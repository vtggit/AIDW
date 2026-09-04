"""Egress destination policy — pure, call-time validation of outbound hosts.

This module decides whether a destination URL's host is permitted for egress,
judging the host **as written** — no DNS resolution, no network, and no file
I/O.  It is deliberately pure so it can be exercised without a database or a
live network.

Denial rules (every mode)
-------------------------
* An empty or missing host.
* The literal ``0.0.0.0``.
* Any IPv4 address in ``169.254.0.0/16`` (link-local).
* Any IPv6 address in ``fe80::/10`` (link-local).

Loopback rules (``EGRESS_POLICY=strict`` only)
----------------------------------------------
* Any IPv4 address in ``127.0.0.0/8``.
* The IPv6 address ``::1``.
* The hostname ``localhost``.

These are denied only when the ``EGRESS_POLICY`` environment variable equals
``strict`` (read at call time, so it can be toggled per call).  With
``EGRESS_POLICY`` unset or any other value the same loopback targets pass.

Exemptions
----------
A comma-separated ``EGRESS_ALLOWED_HOSTS`` environment variable (read at call
time, exact hostname match, surrounding whitespace trimmed per entry) exempts
named hosts from every denial: a URL whose host exactly matches an entry passes
even when that host is loopback, link-local, or ``0.0.0.0``.

Everything else — RFC1918 private addresses (``10.0.0.0/8``,
``172.16.0.0/12``, ``192.168.0.0/16``), public IP literals, and ordinary
hostnames — passes in every mode, including ``EGRESS_POLICY=strict``.
"""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

from app.egress import EgressError

# Environment variable names (read at call time, never at import time).
_POLICY_ENV = "EGRESS_POLICY"
_ALLOWED_HOSTS_ENV = "EGRESS_ALLOWED_HOSTS"

# The strict mode value that enables loopback denial.
_STRICT = "strict"

# The literal "unspecified" IPv4 address, denied in every mode.
_UNSPECIFIED_V4 = "0.0.0.0"

# The loopback hostname, denied in strict mode.
_LOOPBACK_HOSTNAME = "localhost"

# The loopback IPv6 address, denied in strict mode.
_LOOPBACK_V6 = "::1"

# The unspecified IPv6 address, denied in every mode.
_UNSPECIFIED_V6 = ipaddress.ip_address("::")

# Link-local / loopback network ranges.
_LINK_LOCAL_V4 = ipaddress.ip_network("169.254.0.0/16")
_LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")
_LINK_LOCAL_V6 = ipaddress.ip_network("fe80::/10")
_LOOPBACK_V6_NET = ipaddress.ip_network("::1/128")


class EgressDestinationDenied(EgressError):
    """Raised when a destination host is not permitted for egress.

    The message names only the offending host (as written), which is not a
    secret.  No resolved value, credential, or network detail is included.
    """


def _extract_host(url: str) -> str:
    """Return the host component of *url* exactly as written.

    The host is taken from the URL's authority (``netloc``) with any userinfo
    prefix and any port suffix removed.  No DNS resolution or normalization is
    performed — the host is judged as written.  Returns an empty string when
    the URL has no host.
    """
    if not isinstance(url, str):
        return ""
    netloc = urlsplit(url).netloc
    if not netloc:
        return ""
    # Drop any "user:pass@" userinfo prefix.
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    # Drop any ":port" suffix.  For IPv6 literals the port (if present) is
    # separated by the last colon after the closing bracket, so a bracketed
    # host is returned whole.
    if netloc.startswith("["):
        close = netloc.find("]")
        if close != -1:
            return netloc[1:close]
        return netloc[1:]
    if ":" in netloc:
        netloc = netloc.rsplit(":", 1)[0]
    return netloc


def _allowed_hosts() -> set[str]:
    """Return the set of exempt hostnames from ``EGRESS_ALLOWED_HOSTS``.

    The variable is read at call time.  Entries are comma-separated, each
    trimmed of surrounding whitespace, and empty entries are dropped.
    """
    raw = os.environ.get(_ALLOWED_HOSTS_ENV)
    if not raw:
        return set()
    return {entry.strip() for entry in raw.split(",") if entry.strip()}


def _is_strict() -> bool:
    """Return True when ``EGRESS_POLICY`` equals ``strict`` (read at call time)."""
    return os.environ.get(_POLICY_ENV) == _STRICT


_IP_LIKE_RE = re.compile(r"(?:0x[0-9a-fA-F]+|[0-9]+)(?:\.(?:0x[0-9a-fA-F]+|[0-9]+))*")


def _is_ip_like(host: str) -> bool:
    """Return True if *host* looks like an IP address but may not be canonical.

    Matches hosts composed solely of decimal digits, dots, and ``0x``-prefixed
    hexadecimal labels (e.g. ``127.1``, ``0x7f000001``, ``0177.0.0.1``).
    """
    return _IP_LIKE_RE.fullmatch(host) is not None


def _is_canonical_ipv4(host: str) -> bool:
    """Return True if *host* is a canonical dotted-quad IPv4 literal.

    Canonical means exactly four decimal octets, each 0-255, with no leading
    zeros (the single digit ``0`` is allowed).
    """
    parts = host.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part or not all(c in "0123456789" for c in part):
            return False
        if len(part) > 1 and part[0] == "0":
            return False
        if int(part) > 255:
            return False
    return True


def _denied_reason(host: str, strict: bool) -> str | None:
    """Return a human-readable denial reason for *host*, or None when allowed.

    The exemption check is the caller's responsibility; this helper only
    classifies the host against the denial rules.
    """
    if not host:
        return "empty or missing host"

    if host == _UNSPECIFIED_V4:
        return "unspecified address 0.0.0.0"

    if host == "::":
        return "unspecified address ::"

    if _is_ip_like(host) and not _is_canonical_ipv4(host):
        return "non-canonical IP-like address"

    # IPv4 literal classification.
    try:
        v4 = ipaddress.ip_address(host)
    except ValueError:
        v4 = None
    if v4 is not None and v4.version == 4:
        if v4 in _LINK_LOCAL_V4:
            return "link-local IPv4 address (169.254.0.0/16)"
        if strict and v4 in _LOOPBACK_V4:
            return "loopback IPv4 address (127.0.0.0/8)"
        return None

    # IPv6 literal classification.
    try:
        v6 = ipaddress.ip_address(host)
    except ValueError:
        v6 = None
    if v6 is not None and v6.version == 6:
        if v6 == _UNSPECIFIED_V6:
            return "unspecified address ::"
        if v6 in _LINK_LOCAL_V6:
            return "link-local IPv6 address (fe80::/10)"
        if strict and v6 in _LOOPBACK_V6_NET:
            return "loopback IPv6 address (::1)"
        mapped_v4 = v6.ipv4_mapped
        if mapped_v4 is not None:
            if mapped_v4 == ipaddress.ip_address(_UNSPECIFIED_V4):
                return "unspecified address 0.0.0.0"
            if mapped_v4 in _LINK_LOCAL_V4:
                return "link-local IPv4 address (169.254.0.0/16)"
            if strict and mapped_v4 in _LOOPBACK_V4:
                return "loopback IPv4 address (127.0.0.0/8)"
        return None

    # Not an IP literal — a hostname.  Loopback hostnames are denied in
    # strict mode: the bare name (any case, optional trailing dot), any
    # subdomain of the ``localhost`` TLD, and the common alias
    # ``localhost.localdomain``.
    if strict:
        normalized = host.lower().rstrip(".")
        if (
            normalized == _LOOPBACK_HOSTNAME
            or normalized.endswith("." + _LOOPBACK_HOSTNAME)
            or normalized == _LOOPBACK_HOSTNAME + ".localdomain"
        ):
            return "loopback hostname 'localhost'"
    return None


def validate_destination(url: str) -> None:
    """Validate that the host of *url* is permitted for egress.

    The host is judged as written (no DNS resolution, no network, no file I/O).
    Environment variables ``EGRESS_POLICY`` and ``EGRESS_ALLOWED_HOSTS`` are
    read at call time.

    Args:
        url: The destination URL to validate.

    Raises:
        EgressDestinationDenied: When the host is denied (empty/missing host,
            ``0.0.0.0``, link-local IPv4/IPv6, or — in strict mode — loopback
            IPv4/IPv6/``localhost``) and the host is not exempted by
            ``EGRESS_ALLOWED_HOSTS``.
    """
    try:
        host = _extract_host(url)
    except ValueError:
        raise EgressDestinationDenied(
            f"Egress destination denied: invalid bracketed host ({url!r})"
        )
    allowed = _allowed_hosts()
    if host.lower() in {h.lower() for h in allowed}:
        return
    strict = _is_strict()
    reason = _denied_reason(host, strict)
    if reason is not None:
        raise EgressDestinationDenied(f"Egress destination denied: {reason} ({host!r})")
