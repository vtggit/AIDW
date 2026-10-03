"""OData page-URL builder for cursor ingest.

Pure string construction, no network: given the connection endpoint, the entity set, and an
optional (cursor field, watermark, kind), build the ``$top``/``$orderby``/``$filter`` page URL.
Literal style is kind- and protocol-aware: numerics are validated bare literals, V2 timestamps use
the ``datetime'...'`` literal form, V4 timestamps are bare ISO-8601, and string literals are
single-quoted with embedded quotes doubled (the OData escape). Parameter values are
percent-encoded, and a literal ``&`` in a watermark (hostile payload) stays encoded — an
unencoded ``&`` would split the query string into a stray parameter and break the page URL.
"""

import math
import urllib.parse
from datetime import datetime, timezone

# Sub-delims safe to leave raw inside a query string. ``&`` (and ``;``) are deliberately NOT in
# the set: they separate query parameters, so a literal ``&`` in a filter value must be
# percent-encoded or it would break the page URL into a stray parameter.
_QUERY_SAFE = "$=,()'"


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
    a watermark exists, filtered to rows at-or-after the watermark. That at-or-after (``ge``)
    comparison is rendered as ``field gt X or field eq X`` — OData comparison operators bind
    tighter than ``or``, so it selects exactly the rows ``ge X`` would: rows sharing the
    watermark value are re-read rather than skipped. Safe because records upsert by business
    key, so the re-read adds no duplicates while a tie group at the watermark can never be lost
    to the filter."""
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
                + urllib.parse.quote(
                    f"{cursor_field} gt {literal} or {cursor_field} eq {literal}",
                    safe=_QUERY_SAFE,
                )
            )
    return f"{base}/{urllib.parse.quote(entity_set)}?{'&'.join(parts)}"
