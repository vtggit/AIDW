"""Chart data for dashboard items (interim in-API egress path).

Resolves a dashboard item's role-tagged fields to its dataset, fetches a sampled data page
from the live source (the same egress seam profiling uses), and aggregates it into a labeled
series the warehouse UI can draw. There is deliberately no local row store to query yet — the
Milestone-6 typed landing tables carry the payload columns; when they land, only the row
source here changes (SQL over the landing table replaces the live sample).

RTBF (#76): a chart is value-level output — the group labels ARE row values — so unlike
profiling (which keeps the non-personal COUNTS full-sample and filters only the value
columns), suppressed subjects are dropped from the ENTIRE aggregation, totals included, and
``sample_size`` is reported POST-suppression: the erased subject is invisible, not visibly
redacted (a pre/post pair would telegraph exactly how many rows were erased). The
suppression list is read AFTER the live fetch (matching profiling's ordering) so an erasure
committed during the fetch window still applies. Same fail-closed contract as
profiling/ingest: hashing happens only when the dataset actually has suppression entries
(no pepper needed otherwise), and a missing pepper then raises rather than serving the
erased subject. Key derivation (is_key fields in field_position order) matches ingest
exactly, so the hashes line up with what the erasure recorded.

PII: an item referencing a field with an ACTIVE flag ('flagged' or 'confirmed') is withheld
outright — charts must never surface a PII field's values, and a pending review reads as
PII until decided (mirrors profiling's detect-before-write withholding).
"""

import logging
import urllib.parse
import urllib.request

from app.db.connection import get_cursor
from app.governance.hashing import subject_key_hash
from app.ingest.mapper import business_key, parse_rows

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 200  # same sampled-page cap as profiling
_MAX_BUCKETS = 20  # series cap; the remainder is reported via buckets_total/truncated
_LABEL_MAX = 120


class ChartDataError(Exception):
    """A chart-data precondition failed (unchartable item, withheld field, fetch failure)."""


def _fetch_rows(url: str) -> bytes:
    """Fetch a raw data page. Factored out so tests can substitute a fixture without the network."""
    return urllib.request.urlopen(url, timeout=30).read()


def _numeric(v):
    """float(value) or None — charts skip missing/unparseable measure values."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _label(v) -> str:
    """String projection of a dimension value for a series label (None gets its own bucket)."""
    s = "(blank)" if v is None else str(v)
    return s[:_LABEL_MAX]


def _series(rows: list[dict], agg: str, dimension: dict | None, measure: dict | None):
    """Aggregate sampled rows into [(label, value)] pairs plus the pre-cap bucket count.

    No dimension = KPI shape: a single point over the whole sample. With a dimension the
    pairs sort chronologically for a temporal axis (labels ascending) and biggest-first
    otherwise, with the label as a deterministic tiebreak.
    """
    if dimension is None:
        if agg == "count":
            return [(None, len(rows))], 1
        nums = [
            n for n in (_numeric(r.get(measure["name"])) for r in rows) if n is not None
        ]
        if agg == "sum":
            return [(None, round(sum(nums), 4))], 1
        if not nums:  # avg over zero parseable values has no honest single point
            return [], 0
        return [(None, round(sum(nums) / len(nums), 4))], 1

    groups: dict[str, list[float]] = {}
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
        pairs.sort(key=lambda p: p[0])  # time axis: chronological labels
    else:
        pairs.sort(key=lambda p: (-p[1], p[0]))  # biggest buckets first, label tiebreak
    return pairs[:_MAX_BUCKETS], len(pairs)


def item_data(item_id: str) -> dict:
    """Aggregate a sampled data page into the item's chart series.

    Raises LookupError if the item doesn't exist, ChartDataError when it can't be charted
    (no resolvable dataset, PII-withheld field, unchartable aggregation, fetch failure),
    and RuntimeError — fail closed — when suppression entries exist but the pepper is missing.
    """
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dashboard_items WHERE id = %s", (item_id,))
        item = cur.fetchone()
        if item is None:
            raise LookupError("dashboard item not found")

        cur.execute(
            "SELECT dif.field_role, df.id, df.name, df.dataset_id "
            "FROM dashboard_item_fields dif "
            "JOIN discovered_fields df ON df.id = dif.discovered_field_id "
            "WHERE dif.dashboard_item_id = %s "
            "ORDER BY df.field_position NULLS LAST, df.name",
            (item_id,),
        )
        fields = [dict(r) for r in cur.fetchall()]

        dataset_ids = {f["dataset_id"] for f in fields}
        if len(dataset_ids) > 1:
            raise ChartDataError("item fields span multiple datasets")
        dataset_id = next(iter(dataset_ids), None)
        if dataset_id is None:
            # field-less item (e.g. a row-count KPI): resolve the dataset via its suggestion
            cur.execute(
                "SELECT dataset_id FROM suggestions WHERE id = %s",
                (item.get("source_suggestion_id"),),
            )
            row = cur.fetchone()
            dataset_id = row["dataset_id"] if row else None
        if dataset_id is None:
            raise ChartDataError(
                "item has no fields or source suggestion to resolve a dataset"
            )

        cur.execute(
            "SELECT id, name, source_id FROM datasets WHERE id = %s", (dataset_id,)
        )
        ds = cur.fetchone()
        if ds is None:
            raise ChartDataError("item dataset no longer exists")

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
            raise ChartDataError(
                "withheld: field(s) "
                + ", ".join(withheld)
                + " carry an active PII flag"
            )

    agg = (item.get("aggregation") or "").lower()
    if agg not in ("count", "sum", "avg"):
        raise ChartDataError(f"aggregation '{agg or 'none'}' is not chartable")
    dimension = next(
        (f for f in fields if f["field_role"] == "dimension"), None
    ) or next((f for f in fields if f["field_role"] == "temporal"), None)
    measure = next((f for f in fields if f["field_role"] == "measure"), None)
    if agg in ("sum", "avg") and measure is None:
        raise ChartDataError(f"aggregation '{agg}' needs a measure field")

    if conn is None or not (conn.get("endpoint") or "").strip():
        raise ChartDataError("source has no source_connections endpoint to fetch from")
    base = conn["endpoint"].rstrip("/")
    url = f"{base}/{urllib.parse.quote(ds['name'])}?$top={_SAMPLE_SIZE}&$format=json"
    try:
        rows = parse_rows(_fetch_rows(url))
    except Exception:
        # detail stays server-side (mirrors profiling) — no upstream error text to callers
        logger.exception("chart-data fetch failed for dataset %s", ds["name"])
        raise ChartDataError("could not fetch data from the source")

    # RTBF: the suppression list is read AFTER the fetch (matching profiling's ordering) so
    # an erasure committed while the fetch was in flight still applies to this response.
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

    # Drop erased subjects from the WHOLE aggregation (see module docstring) — hash only
    # when entries exist; a missing pepper then raises (fail closed) in subject_key_hash.
    if suppressed:
        kept = []
        for r in rows:
            bk = business_key(r, key_field_names)
            if bk is not None and subject_key_hash(dataset_id, bk) in suppressed:
                continue  # erased subject: excluded from the chart entirely
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
        "item_type": item.get("item_type"),
        "aggregation": agg,
        "dimension": dimension["name"] if dimension else None,
        "measure": measure["name"] if measure else None,
        # post-suppression by design: never telegraphs how many rows were erased
        "sample_size": len(rows),
        "series": series,
        "buckets_total": buckets_total,
        "truncated": buckets_total > len(series),
    }
