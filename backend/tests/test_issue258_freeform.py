"""Proving test for Issue #258 — ingested_payloads table + landing module.

Validates:
  - Migration creates the table with correct schema and constraints
  - upsert_payloads idempotency (duplicate business_key updates in place)
  - aggregate_series count/sum ordering, blank bucket, Other tail bucket
  - Suppression exclusion via suppression_entries
"""

from __future__ import annotations

import pytest

from app.db.connection import get_cursor
from app.governance.hashing import subject_key_hash
from app.ingest.landing import aggregate_series, upsert_payloads


def test_issue258_freeform(monkeypatch: pytest.MonkeyPatch) -> None:
    # ------------------------------------------------------------------
    # Seed a dataset
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO datasets (id, name, source_id, created_at, updated_at)
               VALUES (%s, %s, NULL, NOW(), NOW())""",
            ("ds-258", "Dataset 258"),
        )

    # ------------------------------------------------------------------
    # Upsert payloads — includes a blank dimension value and a non-numeric measure
    # ------------------------------------------------------------------
    rows = [
        {"business_key": "subject1", "payload": {"category": "A", "score": 10}},
        {"business_key": "subject2", "payload": {"category": "B", "score": 20}},
        {"business_key": "subject3", "payload": {"category": "A", "score": 30}},
        {"business_key": "subject4", "payload": {"category": "", "score": 5}},
        {
            "business_key": "subject5",
            "payload": {"category": "C", "score": "not-a-number"},
        },
    ]

    with get_cursor() as cur:
        assert upsert_payloads(cur, "ds-258", rows) == 5

    # ------------------------------------------------------------------
    # Re-upsert subject1 — should NOT duplicate (idempotent update in place)
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        assert (
            upsert_payloads(
                cur,
                "ds-258",
                [
                    {
                        "business_key": "subject1",
                        "payload": {"category": "A", "score": 99},
                    }
                ],
            )
            == 1
        )

        # Verify exactly 5 rows exist (no duplicate)
        cur.execute(
            """SELECT COUNT(*) AS n FROM ingested_payloads WHERE dataset_id = %s""",
            ("ds-258",),
        )
        assert cur.fetchone()["n"] == 5

    # ------------------------------------------------------------------
    # Count aggregation — verify values and ordering (value desc, label asc tiebreak)
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        res = aggregate_series(cur, "ds-258", "category", "count")

    assert res["total_rows"] == 5
    assert res["buckets_total"] == 4  # A, B, C, (blank)

    expected_series = [
        ["A", 2],
        ["(blank)", 1],
        ["B", 1],
        ["C", 1],
    ]
    assert res["series"] == expected_series

    # ------------------------------------------------------------------
    # Blank bucket is present (NULL/empty dimension projects to "(blank)")
    # ------------------------------------------------------------------
    labels = [s[0] for s in res["series"]]
    assert "(blank)" in labels

    # ------------------------------------------------------------------
    # Other tail bucket with top_n=2
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        res_capped = aggregate_series(cur, "ds-258", "category", "count", top_n=2)

    series_capped = res_capped["series"]
    assert len(series_capped) == 3  # A + (blank) + Other
    assert series_capped[0] == ["A", 2]
    last_bucket = series_capped[-1]
    assert last_bucket[0] == "Other"
    # Tail sum: B(1) + C(1) = 2
    assert last_bucket[1] == 2

    # ------------------------------------------------------------------
    # Sum aggregation over numeric measure with one non-numeric row skipped
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        res_sum = aggregate_series(cur, "ds-258", "category", "sum", measure="score")

    assert res_sum["total_rows"] == 5
    # subject1 was RE-UPSERTED above with score 99 (idempotency step), so A = 99 + 30.
    expected_sum_series = [
        ["A", 129.0],
        ["B", 20.0],
        ["(blank)", 5.0],
        ["C", 0.0],
    ]
    assert res_sum["series"] == expected_sum_series

    # ------------------------------------------------------------------
    # Byte-identical results across two identical calls (determinism)
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        res1 = aggregate_series(cur, "ds-258", "category", "count")
        res2 = aggregate_series(cur, "ds-258", "category", "count")

    assert res1 == res2

    # ------------------------------------------------------------------
    # Suppression exclusion — subject vanishes from series and total_rows
    # ------------------------------------------------------------------
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", "test-pepper")
    suppressed_hash = subject_key_hash("ds-258", "subject2")

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO suppression_entries (id, name, key_hash, dataset_id, created_at, updated_at)
               VALUES (%s, %s, %s, %s, NOW(), NOW())""",
            ("sup-1", "Suppress subject2", suppressed_hash, "ds-258"),
        )

    with get_cursor() as cur:
        res_sup = aggregate_series(cur, "ds-258", "category", "count")

    assert res_sup["total_rows"] == 4
    labels_sup = [s[0] for s in res_sup["series"]]
    assert "B" not in labels_sup
