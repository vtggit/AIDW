"""Pure cursor-based functions for payload upsert and aggregation.

Both functions operate on a passed psycopg2 cursor — no connection management,
no HTTP, stdlib + psycopg2 only.  Suppression exclusion mirrors the logic in
``app.dashboard.data_service``: a row is excluded when
``app.governance.hashing.subject_key_hash`` of its ``business_key`` matches an
active ``suppression_entries`` entry for that dataset.
"""

from __future__ import annotations

import uuid
from typing import Any

from psycopg2.extras import Json


def upsert_payloads(cur: Any, dataset_id: str, rows: list[dict[str, object]]) -> int:
    """Insert or update payloads for *dataset_id*.

    Each element of *rows* must carry ``business_key`` (str) and ``payload``
    (dict).  On conflict on the UNIQUE(dataset_id, business_key) constraint
    the row is updated in place — idempotent re-ingest never duplicates.

    Returns the number of rows written.
    """
    if not rows:
        return 0

    for row in rows:
        payload_dict = row["payload"]
        business_key = str(row["business_key"])
        row_id = uuid.uuid4().hex
        name = payload_dict.get("name", "") if isinstance(payload_dict, dict) else ""
        cur.execute(
            """
            INSERT INTO ingested_payloads (id, name, dataset_id, business_key, payload, ingested_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())
            ON CONFLICT (dataset_id, business_key)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                ingested_at = EXCLUDED.ingested_at,
                updated_at = EXCLUDED.updated_at
            """,
            (row_id, name, dataset_id, business_key, Json(payload_dict)),
        )

    return len(rows)


def aggregate_series(
    cur: Any,
    dataset_id: str,
    dimension: str,
    agg: str,
    measure: str | None = None,
    top_n: int = 20,
) -> dict[str, object]:
    """Compute an aggregation series over the FULL landed payloads in SQL.

    Parameters
    ----------
    cur : psycopg2 cursor (RealDictCursor)
        Active cursor for query execution.
    dataset_id : str
        Scope to a single dataset.
    dimension : str
        JSONB key inside ``payload`` used as the series label.
    agg : {"count", "sum", "avg"}
        Aggregation function.  ``sum`` and ``avg`` require *measure*.
    measure : str or None
        JSONB key whose value is cast to numeric for sum/avg.
    top_n : int
        Maximum number of explicit buckets; remaining tail becomes [Other, …].

    Returns a dict with keys:
        series      – list of [label, value] pairs (value-desc, label-asc tiebreak)
        total_rows  – COUNT of landed rows after suppression exclusion
        buckets_total – pre-cap distinct-label count
        refreshed_at – MAX(ingested_at) as ISO-8601 string or None
    """
    if agg not in ("count", "sum", "avg"):
        raise ValueError(f"Unsupported aggregation: {agg}")
    if agg in ("sum", "avg") and measure is None:
        raise ValueError("measure is required for sum/avg aggregations")

    # Fetch active suppressions for this dataset (key_hash values)
    cur.execute(
        "SELECT key_hash FROM suppression_entries WHERE dataset_id = %s",
        (dataset_id,),
    )
    suppressed_hashes: set[str] = {row["key_hash"] for row in cur.fetchall()}

    ids_filter: tuple[str, ...] | None = None
    if suppressed_hashes:
        from app.governance.hashing import subject_key_hash

        # Fetch all payloads to filter out suppressed subjects locally
        cur.execute(
            "SELECT id, business_key FROM ingested_payloads WHERE dataset_id = %s",
            (dataset_id,),
        )
        all_rows = cur.fetchall()
        valid_ids = tuple(
            r["id"]
            for r in all_rows
            if subject_key_hash(dataset_id, r["business_key"]) not in suppressed_hashes
        )
        ids_filter = valid_ids

    # Placeholder order is TEXTUAL in psycopg2: the bucket query binds
    # label(dimension) -> agg(measure x3) -> where(dataset_id, ids), so the
    # measure params must sit between dimension and the where params — binding
    # them onto a shared list in build order was run 9's TypeError.
    where_clauses: list[str] = ["ip.dataset_id = %s"]
    where_params: list[object] = [dataset_id]

    if ids_filter is not None:
        if len(ids_filter) == 0:
            return {
                "series": [],
                "total_rows": 0,
                "buckets_total": 0,
                "refreshed_at": None,
            }
        where_clauses.append("ip.id IN %s")
        where_params.append(ids_filter)

    where_sql = " AND ".join(where_clauses)

    measure_params: list[object] = []
    if agg == "count":
        agg_expr = "COUNT(*) AS val"
    else:
        fn = "SUM" if agg == "sum" else "AVG"
        agg_expr = (
            f"COALESCE({fn}(CASE WHEN (ip.payload->>%s) IS NOT NULL "
            f"AND (ip.payload->>%s) ~ '^-?[0-9]+(\\.[0-9]+)?$' "
            f"THEN (ip.payload->>%s)::numeric END), 0) AS val"
        )
        measure_params = [measure, measure, measure]

    bucket_query = f"""
        SELECT COALESCE(NULLIF(ip.payload->>%s, ''), '(blank)') AS label, {agg_expr}
        FROM ingested_payloads ip
        WHERE {where_sql}
        GROUP BY label
        ORDER BY val DESC, label ASC
    """
    cur.execute(bucket_query, [dimension] + measure_params + where_params)
    buckets = cur.fetchall()

    total_query = f"SELECT COUNT(*) AS n FROM ingested_payloads ip WHERE {where_sql}"
    cur.execute(total_query, where_params)
    total_rows = cur.fetchone()["n"]

    refresh_query = f"SELECT MAX(ingested_at) AS max_ingested FROM ingested_payloads ip WHERE {where_sql}"
    cur.execute(refresh_query, where_params)
    row = cur.fetchone()
    refreshed_at = row["max_ingested"].isoformat() if row["max_ingested"] else None

    series: list[list[object]] = []
    tail_sum = 0.0
    has_tail = False

    if len(buckets) > top_n:
        for i, b in enumerate(buckets):
            label = b["label"]
            val = float(b["val"]) if b["val"] is not None else 0.0
            if i < top_n:
                series.append([label, val])
            else:
                tail_sum += val
                has_tail = True

        if has_tail:
            series.append(["Other", tail_sum])
    else:
        for b in buckets:
            label = b["label"]
            val = float(b["val"]) if b["val"] is not None else 0.0
            series.append([label, val])

    return {
        "series": series,
        "total_rows": total_rows,
        "buckets_total": len(buckets),
        "refreshed_at": refreshed_at,
    }
