"""Chart wire (#258/#259): landed-path aggregation, ingest write-through, RTBF purge.

Three seams proven together:
  - item_data prefers FULL landed aggregates over the live 200-row sample when the
    warehouse holds the dataset's payloads (source="landed", total_rows, refreshed_at)
  - apply_rows lands each stored row's payload in the same guarded branch as the
    op-log, so a suppressed subject's payload is never stored
  - (the erasure purge of ingested_payloads is asserted in test_deletion_worker's
    end-to-end test, same transaction as the op-log delete)
"""

import uuid

from app.db.connection import get_cursor
from app.governance.hashing import subject_key_hash
from app.ingest.cursor import apply_rows
from app.ingest.landing import upsert_payloads
from tests.test_dashboard_item_data import (
    _accept,
    _data,
    _dataset_id,
    _discover,
)


def test_item_data_prefers_landed_aggregates(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    ds = _dataset_id(sid)

    # The /data route is gated on ENABLE_INAPI_EGRESS (built for the live-sample path;
    # QA runs with it on). NO _fetch_rows patch here — a fetch attempt would blow up,
    # which is itself the proof that the landed path never egresses.
    monkeypatch.setattr("app.api.dashboard_items.ENABLE_INAPI_EGRESS", True)

    with get_cursor() as cur:
        upsert_payloads(
            cur,
            ds,
            [
                {"business_key": f"k{i}", "payload": {"ShipCountry": c}}
                for i, c in enumerate(
                    ["Germany"] * 3 + ["France"] * 2 + ["Brazil"]
                )
            ],
        )

    res = _data(client, admin_headers, item["id"])
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["source"] == "landed"
    assert d["total_rows"] == 6
    assert d["sample_size"] == 6  # post-suppression count, not a sample cap
    assert d["refreshed_at"]
    assert d["series"][0] == {"label": "Germany", "value": 3.0}
    labels = [s["label"] for s in d["series"]]
    assert labels == ["Germany", "France", "Brazil"]


def test_apply_rows_lands_payloads_and_never_stores_suppressed(
    client, admin_headers, monkeypatch
):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", "wire-pepper")
    ds = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (ds, "wire-ds"),
        )
        cur.execute(
            "INSERT INTO suppression_entries (id, name, key_hash, dataset_id, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (uuid.uuid4().hex, "sup", subject_key_hash(ds, "s2"), ds),
        )
        result = apply_rows(
            cur,
            None,
            ds,
            [{"K": "s1", "v": 1}, {"K": "s2", "v": 2}, {"K": "s3", "v": 3}],
            ["K"],
        )
        assert result["rows_written"] == 2
        assert result["rows_suppressed"] == 1

        cur.execute(
            "SELECT business_key, payload FROM ingested_payloads "
            "WHERE dataset_id = %s ORDER BY business_key",
            (ds,),
        )
        rows = cur.fetchall()
    keys = [r["business_key"] for r in rows]
    assert keys == ["s1", "s3"]  # the suppressed subject's payload never landed
    assert rows[0]["payload"] == {"K": "s1", "v": 1}
