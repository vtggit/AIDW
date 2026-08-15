"""Egress HTTP helpers for outbound source-system calls.

This module resolves which stored credential (if any) applies to a given
outbound URL and performs the HTTP fetch with the appropriate
authorization.  It is deliberately dependency-light: it uses only the
standard library for HTTP and the shared ``get_cursor`` helper for
database access.

Security notes:
    * Credentials are resolved by matching the connection ``endpoint``
      (trailing slashes stripped) as the longest prefix of the target
      URL.  The join key between ``source_connections`` and
      ``source_credentials`` is ``source_id`` — the connection's own
      ``id`` column is never used to look up a credential.
    * On HTTP 401/403 the raised :class:`EgressAuthError` message
      contains only the status code and the scheme names parsed from
      the ``WWW-Authenticate`` header.  The credential, principal, or
      secret value is never included.
"""

from __future__ import annotations

import base64
import os
import re
import urllib.error
import urllib.request

from app.db.connection import get_cursor


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


def resolve_secret(secret_ref: str) -> str:
    """Resolve a secret reference to its value.

    The reference is the name of an environment variable; the value is
    read at call time so that tests can monkeypatch it.
    """
    return os.environ.get(secret_ref, "")


def credential_for_url(url: str) -> dict | None:
    """Return the earliest credential row for the connection matching *url*.

    Selection logic:
        1. Find the ``source_connections`` row whose ``endpoint``
           (trailing slashes stripped) is the longest prefix of *url*.
        2. Read that row's ``source_id`` column.
        3. Return the earliest ``source_credentials`` row (by
           ``created_at``) having the same ``source_id``.

    Returns ``None`` when no connection endpoint is a prefix of *url*,
    when the matched connection has a null ``source_id``, or when that
    source has no credential row.
    """
    target = _strip_trailing_slashes(url)

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, endpoint, source_id FROM source_connections WHERE endpoint IS NOT NULL"
        )
        connections = cur.fetchall()

    # Find the connection whose endpoint is the longest prefix of the target.
    best: dict | None = None
    best_len = -1
    for conn in connections:
        endpoint = _strip_trailing_slashes(conn["endpoint"])
        if not endpoint:
            continue
        if target == endpoint or target.startswith(endpoint):
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
            "ORDER BY created_at LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()

    return row


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    """Fetch *url* and return the response body as bytes.

    If a credential is resolved for *url* and its ``auth_scheme`` is
    ``basic``, an ``Authorization: Basic <base64>`` header is added.
    If the scheme is any other non-null value, :class:`EgressError` is
    raised.  If no credential is resolved, the request is made without
    an Authorization header.

    Raises:
        EgressAuthError: on HTTP 401 or 403.
        EgressError: on unsupported auth scheme or other HTTP errors.
    """
    credential = credential_for_url(url)

    if credential is not None:
        auth_scheme = credential.get("auth_scheme")
        if auth_scheme is not None:
            if auth_scheme == "basic":
                principal = credential.get("principal") or ""
                secret_ref = credential.get("secret_ref") or ""
                secret = resolve_secret(secret_ref)
                token = base64.b64encode(f"{principal}:{secret}".encode()).decode(
                    "ascii"
                )
                request = urllib.request.Request(url)
                request.add_header("Authorization", f"Basic {token}")
            else:
                raise EgressError(f"unsupported auth_scheme: {auth_scheme}")
        else:
            request = urllib.request.Request(url)
    else:
        request = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            www_auth = exc.headers.get("WWW-Authenticate") if exc.headers else None
            schemes = _parse_www_authenticate_schemes(www_auth)
            scheme_text = ", ".join(schemes) if schemes else "unknown"
            raise EgressAuthError(
                f"HTTP {exc.code} — authentication failed (scheme: {scheme_text})"
            ) from exc
        raise EgressError(f"HTTP {exc.code} — {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise EgressError(f"URL error: {exc.reason}") from exc
