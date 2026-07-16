"""Computed series for dashboard_items (engine-generated: computed-series lane).

Resolves an item's role-tagged dashboard_item_fields rows to discovered_fields, samples a live
page from the owning datasets row's source_connections endpoint, and aggregates a
labeled series. RTBF: suppressed subjects are dropped from the WHOLE aggregation
and sample_size is reported post-suppression (the erased subject is invisible,
never visibly redacted); the suppression list is read AFTER the fetch; hashing
runs only when entries exist, and a missing pepper then raises (fail closed).
PII: any referenced field with an active flag withholds the whole item.
"""

import logging
import urllib.parse
import urllib.request

from app.db.connection import get_cursor
from app.governance.hashing import subject_key_hash
from app.ingest.mapper import business_key, parse_rows

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 200  # sampled-page cap
_MAX_BUCKETS = 20  # series cap; the remainder is reported, never silently dropped
_LABEL_MAX = 120
_ALLOWED_AGGREGATIONS = ("count", "sum", "avg")  # exactly what the AC enabled


class SeriesDataError(Exception):
    """A series-data precondition failed (unchartable item, withheld field,
    fetch failure)."""


def _fetch_rows(url: str) -> bytes:
    """Fetch a raw data page. Factored out so tests can substitute a fixture
    without the network."""
    return urllib.request.urlopen(url, timeout=30).read()


def _numeric(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _label(v) -> str:
    s = "(blank)" if v is None else str(v)
    return s[:_LABEL_MAX]


def _series(rows, agg, dimension, measure):
    """Aggregate sampled rows into [(label, value)] pairs plus the pre-cap
    bucket count. No dimension = a single point over the whole sample."""
    if dimension is None:
        if agg == "count":
            return [(None, len(rows))], 1
        nums = [
            n for n in (_numeric(r.get(measure["name"])) for r in rows) if n is not None
        ]
        if agg == "sum":
            return [(None, round(sum(nums), 4))], 1
        if not nums:
            return [], 0
        return [(None, round(sum(nums) / len(nums), 4))], 1

    groups = {}
    for r in rows:
        lbl = _label(r.get(dimension["name"]))
        if agg == "count":
            acc = groups.setdefault(lbl, [0.0, 0])
            acc[0] += 1
        else:
            n = _numeric(r.get(measure["name"]))
            if n is None:
                continue
            acc = groups.setdefault(lbl, [0.0, 0])
            acc[0] += n
            acc[1] += 1
    if agg == "count":
        pairs = [(k, int(v[0])) for k, v in groups.items()]
    elif agg == "sum":
        pairs = [(k, round(v[0], 4)) for k, v in groups.items()]
    else:
        pairs = [(k, round(v[0] / v[1], 4)) for k, v in groups.items() if v[1]]

    if dimension["field_role"] == "temporal":
        pairs.sort(key=lambda p: p[0])
    else:
        pairs.sort(key=lambda p: (-p[1], p[0]))
    return pairs[:_MAX_BUCKETS], len(pairs)


def series_data(item_id: str) -> dict:
    """Aggregate a sampled data page into the item's series. Raises LookupError
    for a missing item, SeriesDataError when it cannot be charted, RuntimeError
    (fail closed) when suppression entries exist but the pepper is missing."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM dashboard_items WHERE id = %s",
            (item_id,),
        )
        item = cur.fetchone()
        if item is None:
            raise LookupError("dashboard_item not found")

        cur.execute(
            "SELECT sat.field_role, tgt.id, tgt.name, tgt.dataset_id "
            "FROM dashboard_item_fields sat "
            "JOIN discovered_fields tgt ON tgt.id = sat.discovered_field_id "
            "WHERE sat.dashboard_item_id = %s "
            "ORDER BY tgt.field_position NULLS LAST, tgt.name",
            (item_id,),
        )
        fields = [dict(r) for r in cur.fetchall()]

        dataset_ids = {f["dataset_id"] for f in fields}
        if len(dataset_ids) > 1:
            raise SeriesDataError("item fields span multiple datasets")
        dataset_id = next(iter(dataset_ids), None)
        if dataset_id is None:
            raise SeriesDataError("item has no fields to resolve a dataset")

        cur.execute(
            "SELECT id, name, source_id FROM datasets WHERE id = %s",
            (dataset_id,),
        )
        ds = cur.fetchone()
        if ds is None:
            raise SeriesDataError("item dataset no longer exists")

        cur.execute(
            "SELECT endpoint FROM source_connections WHERE source_id = %s "
            "ORDER BY created_at LIMIT 1",
            (ds["source_id"],),
        )
        conn = cur.fetchone()

        # withhold outright when ANY referenced field carries an active PII flag
        cur.execute(
            "SELECT DISTINCT discovered_field_id FROM pii_flags WHERE dataset_id = %s "
            "AND status IN ('flagged', 'confirmed') AND discovered_field_id IS NOT NULL",
            (dataset_id,),
        )
        flagged = {r["discovered_field_id"] for r in cur.fetchall()}
        withheld = sorted(f["name"] for f in fields if f["id"] in flagged)
        if withheld:
            raise SeriesDataError(
                "withheld: field(s) "
                + ", ".join(withheld)
                + " carry an active PII flag"
            )

    agg = (item.get("aggregation") or "").lower()
    if agg not in _ALLOWED_AGGREGATIONS:
        raise SeriesDataError(
            f"aggregation '{agg or 'none'}' is not enabled for this endpoint"
        )
    dimension = next(
        (f for f in fields if f["field_role"] == "dimension"), None
    ) or next((f for f in fields if f["field_role"] == "temporal"), None)
    measure = next((f for f in fields if f["field_role"] == "measure"), None)
    if agg in ("sum", "avg") and measure is None:
        raise SeriesDataError(f"aggregation '{agg}' needs a measure field")

    if conn is None or not (conn.get("endpoint") or "").strip():
        raise SeriesDataError("source has no connection endpoint to fetch from")
    base = conn["endpoint"].rstrip("/")
    url = f"{base}/{urllib.parse.quote(ds['name'])}?$top={_SAMPLE_SIZE}&$format=json"
    try:
        rows = parse_rows(_fetch_rows(url))
    except Exception:
        # detail stays server-side — no upstream error text to callers
        logger.exception("series fetch failed for dataset %s", ds["name"])
        raise SeriesDataError("could not fetch data from the source")

    # RTBF: the suppression list is read AFTER the fetch so an erasure committed
    # while the fetch was in flight still applies to this response.
    with get_cursor() as cur:
        cur.execute(
            "SELECT name FROM discovered_fields WHERE dataset_id = %s AND is_key "
            "ORDER BY field_position NULLS LAST, name",
            (dataset_id,),
        )
        key_field_names = [r["name"] for r in cur.fetchall()]
        cur.execute(
            "SELECT key_hash FROM suppression_entries WHERE dataset_id = %s",
            (dataset_id,),
        )
        suppressed = {r["key_hash"] for r in cur.fetchall()}

    # Drop erased subjects from the WHOLE aggregation — hash only when entries
    # exist; a missing pepper then raises (fail closed) in subject_key_hash.
    if suppressed:
        kept = []
        for r in rows:
            bk = business_key(r, key_field_names)
            if bk is not None and subject_key_hash(dataset_id, bk) in suppressed:
                continue  # erased subject: excluded from the series entirely
            kept.append(r)
        rows = kept

    pairs, buckets_total = _series(rows, agg, dimension, measure)
    title = item.get("title") or item.get("name") or agg
    series = [
        {"label": title if lbl is None else lbl, "value": val} for lbl, val in pairs
    ]
    return {
        "item_id": item["id"],
        "title": item.get("title"),
        "aggregation": agg,
        "dimension": dimension["name"] if dimension else None,
        "measure": measure["name"] if measure else None,
        # post-suppression by design: never telegraphs how many rows were erased
        "sample_size": len(rows),
        "series": series,
        "buckets_total": buckets_total,
        "truncated": buckets_total > len(series),
    }
