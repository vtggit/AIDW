"""Egress HTTP helpers for outbound source-system calls.

This module resolves which stored credential (if any) applies to a given
outbound URL and performs the HTTP fetch with the appropriate
authorization.  It is deliberately dependency-light: it uses only the
standard library for HTTP and the shared ``get_cursor`` helper for
database access.

Security notes:
    * Credentials are resolved by matching the connection ``endpoint``
      against the target URL on an **origin and path boundary**: the
      endpoint's scheme, host, and effective port must each equal the
      target's (case-insensitive for scheme and host), and the endpoint's
      path (dot segments normalized per RFC 3986) must be a prefix of the
      target's path that ends on a path-segment boundary (``/``).  A
      longer sibling host, a different port, a different scheme, or a
      path that merely shares a textual prefix does not resolve another
      endpoint's credential.  The join key between
      ``source_connections`` and ``source_credentials`` is
      ``source_id`` — the connection's own ``id`` column is never used
      to look up a credential.
    * When a source has multiple ``source_credentials`` rows, the
      intended **active** credential is selected deterministically (the
      most recently created row, ties broken by id) rather than the
      earliest, so a rotated credential takes effect.
    * A URL that resolves to a credential whose ``auth_scheme`` is
      unsupported, or that resolves to no credential at all, performs the
      anonymous fetch the pre-egress callers performed instead of
      failing closed before the request.
    * On HTTP 401/403 the raised :class:`EgressAuthError` message
      contains only the status code and the scheme names parsed from
      the ``WWW-Authenticate`` header.  The credential, principal, or
      secret value is never included.
    * The ``Authorization`` header is re-attached on a redirect only
      when the redirect target's *effective origin* (scheme, lower-cased
      host, and effective port with default ports normalized) equals the
      original request's effective origin.  A scheme downgrade (https to
      http), a port change, or a host change all drop the header.  A
      malformed or unparseable redirect port is treated as an origin
      mismatch and the header is omitted.
"""

from __future__ import annotations

import base64
import re
import urllib.error
import urllib.parse
import urllib.request

from app.db.connection import get_cursor
from app.egress import SecretRefInvalid, SecretUnavailable
from app.egress.policy import validate_destination
from app.egress.secrets import resolve_secret


class EgressError(Exception):
    """Base error for egress HTTP operations."""


class EgressAuthError(EgressError):
    """Raised when the remote endpoint rejects the supplied credentials.

    The message contains only the HTTP status code and the scheme names
    parsed from the ``WWW-Authenticate`` response header.
    """


def _strip_trailing_slashes(value: str) -> str:
    """Remove trailing slashes from a URL string."""
    return value.rstrip("/")


def _parse_www_authenticate_schemes(header_value: str | None) -> list[str]:
    """Extract scheme names from a ``WWW-Authenticate`` header value.

    A header such as ``Basic charset="UTF-8"`` yields ``["Basic"]``.
    Multiple comma-separated challenges are each parsed.
    """
    if not header_value:
        return []
    schemes: list[str] = []
    for challenge in header_value.split(","):
        challenge = challenge.strip()
        if not challenge:
            continue
        # The scheme is the first token before any space or equals sign.
        match = re.match(r"^([A-Za-z][A-Za-z0-9._-]*)", challenge)
        if match:
            schemes.append(match.group(1))
    return schemes


class SecretUnavailableAuthError(EgressAuthError, SecretUnavailable):
    """Raised when a referenced environment variable is unset or empty."""


class SecretRefInvalidAuthError(EgressAuthError, SecretRefInvalid):
    """Raised when a secret reference is malformed."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that suppresses automatic redirect following."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _effective_origin(url: str) -> tuple[str, str, int] | None:
    """Return the effective origin ``(scheme, host, port)`` of *url*.

    The scheme is lower-cased, the host is lower-cased, and the port is
    the URL's explicit port when present and parseable, otherwise the
    scheme's default port (80 for http, 443 for https).  Returns ``None``
    when the URL has no host, its explicit port is malformed or
    unparseable, or the scheme is not http/https.
    """
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    try:
        explicit_port = parsed.port
    except (ValueError, TypeError):
        return None
    if explicit_port is None:
        if scheme == "http":
            port = 80
        elif scheme == "https":
            port = 443
        else:
            return None
    else:
        port = explicit_port
    return (scheme, host, port)


def _effective_port(parsed: urllib.parse.ParseResult) -> int:
    """Return the effective port of a parsed URL.

    The explicit port when present and parseable, otherwise the scheme's
    default port (80 for http, 443 for https), or 0 when the scheme has
    no default.  Comparing effective ports means an endpoint on one port
    never resolves a credential for a target on a different port.
    """
    try:
        explicit = parsed.port
    except (ValueError, TypeError):
        explicit = None
    if explicit is not None:
        return explicit
    scheme = (parsed.scheme or "").lower()
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return 0


def _normalize_path(path: str) -> str:
    """Remove dot segments from a URL path per RFC 3986 §5.2.4.

    ``/api/../secret`` normalizes to ``/secret`` so that a path that
    merely contains a dot segment is compared on its effective path, not
    its raw textual form.  An empty path stays empty.
    """
    if not path:
        return ""
    output: list[str] = []
    for segment in path.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if output:
                output.pop()
            continue
        output.append(segment)
    result = "/".join(output)
    if path.startswith("/") and not result.startswith("/"):
        result = "/" + result
    return result


def _endpoint_matches_target(endpoint: str, target: str) -> bool:
    """Return True when *endpoint* matches *target* on an origin and path boundary.

    The endpoint's scheme, host, and effective port must each equal the
    target's (case-insensitive for scheme and host), and the endpoint's
    path (dot segments normalized) must be a prefix of the target's path
    that ends on a path-segment boundary (``/``).  A longer sibling host,
    a different port, a different scheme, or a path that merely shares a
    textual prefix does not match.
    """
    ep = urllib.parse.urlparse(endpoint)
    tg = urllib.parse.urlparse(target)

    if (ep.scheme or "").lower() != (tg.scheme or "").lower():
        return False

    ep_host = (ep.hostname or "").lower()
    tg_host = (tg.hostname or "").lower()
    if not ep_host or ep_host != tg_host:
        return False

    if _effective_port(ep) != _effective_port(tg):
        return False

    ep_path = _normalize_path(ep.path or "")
    tg_path = _normalize_path(tg.path or "")

    if ep_path == tg_path:
        return True
    if ep_path == "":
        return True
    if not ep_path.endswith("/"):
        ep_path += "/"
    return tg_path.startswith(ep_path)


def credential_for_url(url: str) -> dict | None:
    """Return the active credential row for the connection matching *url*.

    Selection logic:
        1. Find the ``source_connections`` row whose ``endpoint`` matches
           *url* on an origin and path boundary (exact scheme, host, and
           effective port, plus a path prefix ending on a segment
           boundary), preferring the longest matching endpoint.
        2. Read that row's ``source_id`` column.
        3. Return the intended **active** ``source_credentials`` row for
           that ``source_id`` — the most recently created row, ties
           broken by id — so a rotated credential takes effect.

    Returns ``None`` when no connection endpoint matches *url*, when the
    matched connection has a null ``source_id``, or when that source has
    no credential row.
    """
    target = _strip_trailing_slashes(url)

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, endpoint, source_id FROM source_connections WHERE endpoint IS NOT NULL"
        )
        connections = cur.fetchall()

    # Find the connection whose endpoint matches the target on an origin and
    # path boundary, preferring the longest matching endpoint.
    best: dict | None = None
    best_len = -1
    for conn in connections:
        endpoint = _strip_trailing_slashes(conn["endpoint"])
        if not endpoint:
            continue
        if _endpoint_matches_target(endpoint, target):
            if len(endpoint) > best_len:
                best = conn
                best_len = len(endpoint)

    if best is None:
        return None

    source_id = best["source_id"]
    if source_id is None:
        return None

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, auth_scheme, principal, secret_ref, token_endpoint, "
            "source_id, created_at, updated_at "
            "FROM source_credentials WHERE source_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()

    return row


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    """Fetch *url* and return the response body as bytes.

    Redirects are followed manually (at most 3 hops).  Each redirect
    target is validated via :func:`validate_destination` before the
    request is sent.  The ``Authorization`` header (when a credential is
    resolved) is re-attached on a redirect only when the redirect
    target's effective origin (scheme, lower-cased host, and effective
    port with default ports normalized) equals the original request's
    effective origin; otherwise it is omitted.  A malformed or
    unparseable redirect port is treated as an origin mismatch.

    A URL that resolves to no credential, or to a credential whose
    ``auth_scheme`` is unsupported, performs the anonymous fetch the
    pre-egress callers performed (no ``Authorization`` header) rather
    than failing closed before the request.

    Raises:
        EgressAuthError: on HTTP 401 or 403.
        EgressError: on too many redirects or other HTTP errors.
    """
    validate_destination(url)
    credential = credential_for_url(url)

    original_origin = _effective_origin(url)

    auth_header: str | None = None
    if credential is not None:
        auth_scheme = credential.get("auth_scheme")
        if auth_scheme is not None:
            if auth_scheme == "basic":
                principal = credential.get("principal") or ""
                if not principal.strip():
                    raise EgressAuthError("credential principal is empty or whitespace")
                secret_ref = credential.get("secret_ref") or ""
                try:
                    secret = resolve_secret(secret_ref)
                except SecretUnavailable as exc:
                    raise SecretUnavailableAuthError(str(exc)) from exc
                except SecretRefInvalid as exc:
                    raise SecretRefInvalidAuthError(str(exc)) from exc
                token = base64.b64encode(f"{principal}:{secret}".encode()).decode(
                    "ascii"
                )
                auth_header = f"Basic {token}"
            # An unsupported auth_scheme falls through to an anonymous fetch
            # (no Authorization header) rather than failing closed.

    opener = urllib.request.build_opener(_NoRedirectHandler)
    current_url = url
    max_hops = 3
    hop_count = 0

    while True:
        request = urllib.request.Request(current_url)
        if auth_header is not None:
            current_origin = _effective_origin(current_url)
            if (
                original_origin is not None
                and current_origin is not None
                and current_origin == original_origin
            ):
                request.add_header("Authorization", auth_header)

        try:
            with opener.open(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                hop_count += 1
                if hop_count > max_hops:
                    raise EgressError(
                        f"too many redirects (max {max_hops} hops)"
                    ) from exc
                location = exc.headers.get("Location")
                if location is None:
                    raise EgressError(
                        f"HTTP {exc.code} — missing Location header"
                    ) from exc
                if not location.startswith(("http://", "https://")):
                    location = urllib.parse.urljoin(current_url, location)
                validate_destination(location)
                current_url = location
                continue
            if exc.code in (401, 403):
                www_auth = exc.headers.get("WWW-Authenticate") if exc.headers else None
                schemes = _parse_www_authenticate_schemes(www_auth)
                scheme_text = ", ".join(schemes) if schemes else "unknown"
                raise EgressAuthError(
                    f"HTTP {exc.code} — authentication failed "
                    f"(scheme: {scheme_text})"
                ) from exc
            raise EgressError(f"HTTP {exc.code} — {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise EgressError(f"URL error: {exc.reason}") from exc
