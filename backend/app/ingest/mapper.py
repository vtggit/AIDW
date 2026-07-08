"""OData data-page → row mapping for ingest.

Pure functions, no network and no database: extract the row list from a V2/V4 JSON payload,
derive each row's business key from the dataset's key fields, and project cursor values to
comparable strings. ``normalize_cursor_value`` folds the OData V2 JSON date form
(``/Date(857439600000)/``) into its millisecond count so watermark comparison stays kind-aware
instead of lexicographic-on-noise.
"""

import json
import re

# {1,15} digits bounds the extraction (datetime's year-9999 max is ~2.53e14 ms = 15 digits);
# range VALIDATION happens where a value is considered as a watermark candidate
# (app.ingest.cursor._acceptable) — an absurd remote value stays an opaque string here
_V2_DATE = re.compile(r"^/Date\((-?\d{1,15})(?:[+-]\d{1,4})?\)/$")

_KEY_MAX = 255


def extract_entries(raw: bytes) -> list:
    """Extract the raw entry list from an OData JSON payload — V4 (``value``) or V2
    (``d.results``) — WITHOUT filtering. Callers that reason about the $top page cap need the
    entry count as fetched (a junk entry still occupied a page slot)."""
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("value"), list):
            return data["value"]
        d = data.get("d")
        if isinstance(d, dict) and isinstance(d.get("results"), list):
            return d["results"]
        if isinstance(d, list):
            return d
    return []


def parse_rows(raw: bytes) -> list[dict]:
    """Extract the row list from an OData JSON payload — V4 (``value``) or V2 (``d.results``)."""
    return [r for r in extract_entries(raw) if isinstance(r, dict)]


def business_key(row: dict, key_fields: list[str]) -> str | None:
    """Join the row's key-field values with ``|`` (order given by the caller). Returns None when
    any key value is missing/None — such a row cannot be idempotently replayed, so the caller
    skips it and counts it."""
    parts = []
    for field in key_fields:
        value = row.get(field)
        if value is None:
            return None
        parts.append(str(value))
    return "|".join(parts)[:_KEY_MAX]


def normalize_cursor_value(value) -> str | None:
    """Project a row's cursor-field value to a comparable string. V2 ``/Date(ms)/`` becomes its
    millisecond count (compare as numeric); everything else is ``str()``-projected (ISO-8601
    timestamps compare correctly as text)."""
    if value is None:
        return None
    s = str(value)
    m = _V2_DATE.match(s)
    if m:
        return m.group(1)
    return s[:_KEY_MAX]
