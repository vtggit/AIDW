"""Proving test for Issue #836 — aggregate_series sorts independently of DB order."""

from __future__ import annotations

from app.db.connection import get_cursor
from app.ingest.landing import aggregate_series, upsert_payloads


class _ReversedCursor:
    """Wraps a cursor: passes execute/fetchone through, reverses fetchall."""

    def __init__(self, inner):
        self._inner = inner

    def execute(self, *args, **kwargs):
        return self._inner.execute(*args, **kwargs)

    def fetchone(self):
        return self._inner.fetchone()

    def fetchall(self):
        return list(reversed(self._inner.fetchall()))


def test_issue836_surgical() -> None:
    ds_id = "ds-836"

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO datasets (id, name, source_id, created_at, updated_at)
               VALUES (%s, %s, NULL, NOW(), NOW())""",
            (ds_id, "Dataset 836"),
        )

    rows = [
        {"business_key": "s1", "payload": {"dim": "Z"}},
        {"business_key": "s2", "payload": {"dim": "Z"}},
        {"business_key": "s3", "payload": {"dim": "a"}},
        {"business_key": "s4", "payload": {"dim": "B"}},
        {"business_key": "s5", "payload": {"dim": "_x"}},
        {"business_key": "s6", "payload": {"dim": ""}},
    ]

    with get_cursor() as cur:
        assert upsert_payloads(cur, ds_id, rows) == 6

    # Normal call: value-desc then label-asc (Unicode code points)
    with get_cursor() as cur:
        res = aggregate_series(cur, ds_id, "dim", "count")

    labels = [s[0] for s in res["series"]]
    assert labels == ["Z", "(blank)", "B", "_x", "a"]
    assert res["total_rows"] == 6
    assert res["buckets_total"] == 5

    # Reversed-cursor wrapper: identical series
    with get_cursor() as cur:
        wrapped = _ReversedCursor(cur)
        res_rev = aggregate_series(wrapped, ds_id, "dim", "count")

    assert res_rev["series"] == res["series"]

    # top_n=2: Z(2), (blank)(1), Other(3)
    with get_cursor() as cur:
        res_capped = aggregate_series(cur, ds_id, "dim", "count", top_n=2)

    assert res_capped["series"] == [["Z", 2], ["(blank)", 1], ["Other", 3]]
