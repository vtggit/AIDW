"""OData page-URL builder for cursor ingest.

Pure string construction, no network: given the connection endpoint, the entity set, and an
optional (cursor field, watermark, kind), build the ``$top``/``$orderby``/``$filter`` page URL.
Literal style is kind- and protocol-aware: numerics are validated bare literals, V2 timestamps use
the ``datetime'...'`` literal form, V4 timestamps are bare ISO-8601, and string literals are
single-quoted with embedded quotes doubled (the OData escape).
"""

import math
import urllib.parse
from datetime import datetime, timezone

_QUERY_SAFE = "$=&,()'"


def _filter_literal(
    watermark: str, cursor_kind: str | None, protocol_version: str | None
) -> str:
    kind = (cursor_kind or "string").lower()
    if kind == "numeric":
        # fail loud on anything that isn't a finite number — no injection, no 'gt inf' literals
        if not math.isfinite(float(watermark)):
            raise ValueError(f"non-finite numeric watermark: {watermark!r}")
        return watermark
    if kind == "timestamp":
        if watermark.lstrip("-").isdigit():
            # a normalized V2 /Date(ms)/ watermark: only V2 payloads produce these, so render
            # the V2 datetime literal of its ISO projection
            try:
                iso = datetime.fromtimestamp(
                    int(watermark) / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S")
            except (ValueError, OverflowError, OSError) as exc:
                raise ValueError(
                    f"timestamp watermark out of datetime range: {watermark!r}"
                ) from exc
            return f"datetime'{iso}'"
        if (protocol_version or "").upper().startswith("V2"):
            return f"datetime'{watermark.rstrip('Z')}'"
        return watermark
    escaped = watermark.replace("'", "''")
    return f"'{escaped}'"


def build_page_url(
    endpoint: str,
    entity_set: str,
    top: int,
    protocol_version: str | None = None,
    cursor_field: str | None = None,
    watermark: str | None = None,
    cursor_kind: str | None = None,
) -> str:
    """Build the data-page URL for one ingest fetch. With no cursor field the page is a plain
    ``$top`` sample of the set; with a cursor field the page is ordered by it ascending and, once
    a watermark exists, filtered to strictly-later rows."""
    base = endpoint.rstrip("/")
    parts = [f"$top={int(top)}", "$format=json"]
    if cursor_field:
        parts.append(
            "$orderby=" + urllib.parse.quote(f"{cursor_field} asc", safe=_QUERY_SAFE)
        )
        if watermark is not None and watermark != "":
            literal = _filter_literal(watermark, cursor_kind, protocol_version)
            parts.append(
                "$filter="
                + urllib.parse.quote(f"{cursor_field} gt {literal}", safe=_QUERY_SAFE)
            )
    return f"{base}/{urllib.parse.quote(entity_set)}?{'&'.join(parts)}"
