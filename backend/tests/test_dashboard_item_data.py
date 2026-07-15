"""Chart-data endpoint: GET /api/dashboard-items/{id}/data.

An accepted item's chart series is aggregated from a sampled live page (mocked egress, real
Postgres): count group-by for dimensions, sum/avg over a measure, KPI single-point when there
is no dimension, temporal ordering for line items. Suppressed subjects (RTBF #76) are dropped
from the WHOLE aggregation — chart labels are row values — with the same fail-closed pepper
contract profiling pins; PII-flagged fields make the item withhold outright (422).
"""

import json
import uuid

import pytest

# Same rich Orders schema the suggestion engine turns into the full item mix:
# "Orders by ShipCountry" (bar/count/dimension), "Freight by ShipCountry" (sum),
# "Total Freight" (KPI sum, measure only), "Total Orders" (KPI count, NO fields),
# "Freight over OrderDate" (line, temporal).
_RICH_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NW" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Order">
        <Key><PropertyRef Name="OrderID"/></Key>
        <Property Name="OrderID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="OrderDate" Type="Edm.DateTimeOffset"/>
        <Property Name="Freight" Type="Edm.Decimal"/>
        <Property Name="ShipCountry" Type="Edm.String"/>
        <Property Name="CustomerID" Type="Edm.Int32"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Orders" EntityType="NW.Order"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

# ShipCountry cycles USA/UK/France over 10 rows -> USA x4 (i=0,3,6,9), UK x3, France x3.
# Freight = 10 + i -> sums: USA 58 (10+13+16+19), UK 42 (11+14+17), France 45 (12+15+18).
_ROWS = [
    {
        "OrderID": i,
        "OrderDate": "1998-05-01T00:00:00Z",
        "Freight": 10.0 + i,
        "ShipCountry": ["USA", "UK", "France"][i % 3],
        "CustomerID": 100 + i,
    }
    for i in range(10)
]
_ROWS_JSON = json.dumps({"value": _ROWS}).encode()

PEPPER = "chart-fixture-pepper"


def _make_odata_source(client, admin_headers, endpoint="https://svc.example/odata"):
    sid = client.post(
        "/api/sources", json={"name": "nw", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={
            "name": "conn",
            "endpoint": endpoint,
            "protocol_version": "V4",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/odata-service-configs",
        json={
            "name": "cfg",
            "metadata_path": "$metadata",
            "default_entity_set": "Orders",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    return sid


def _discover(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _RICH_EDMX)
    sid = _make_odata_source(client, admin_headers)
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    return sid


def _suggestions_for_source(client, admin_headers, sid):
    ds_ids = {
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    }
    return [
        s
        for s in client.get("/api/suggestions", headers=admin_headers).json()
        if s.get("dataset_id") in ds_ids
    ]


def _accept(client, admin_headers, sid, title):
    sug = next(
        s
        for s in _suggestions_for_source(client, admin_headers, sid)
        if s["title"] == title
    )
    return client.post(
        f"/api/suggestions/{sug['id']}/accept", headers=admin_headers
    ).json()


def _enable_data(monkeypatch, rows_json=_ROWS_JSON):
    monkeypatch.setattr("app.api.dashboard_items.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.dashboard.data_service._fetch_rows", lambda url: rows_json)


def _data(client, headers, item_id):
    return client.get(f"/api/dashboard-items/{item_id}/data", headers=headers)


def _dataset_id(sid):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT id FROM datasets WHERE source_id = %s", (sid,))
        return cur.fetchone()["id"]


def _field_id(ds, name):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM discovered_fields WHERE dataset_id = %s AND name = %s",
            (ds, name),
        )
        return cur.fetchone()["id"]


def _business_key_of(ds, row):
    from app.db.connection import get_cursor
    from app.ingest.mapper import business_key

    with get_cursor() as cur:
        cur.execute(
            "SELECT name FROM discovered_fields WHERE dataset_id = %s AND is_key "
            "ORDER BY field_position NULLS LAST, name",
            (ds,),
        )
        key_names = [r["name"] for r in cur.fetchall()]
    return business_key(row, key_names)


def _suppress(ds, key):
    from app.db.connection import get_cursor
    from app.governance.hashing import subject_key_hash

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO suppression_entries (id, name, key_hash, dataset_id) "
            "VALUES (%s, 'suppr', %s, %s) ON CONFLICT (key_hash) DO NOTHING",
            (uuid.uuid4().hex, subject_key_hash(ds, key), ds),
        )


# --------------------------------------------------------------------------- pure helper


def test_series_avg_by_dimension():
    """The engine emits count/sum today; 'avg' is in the aggregation CHECK, so the helper
    supports it — pinned here directly since no engine-emitted suggestion exercises it.
    """
    from app.dashboard.data_service import _series

    rows = [
        {"C": "A", "V": 10},
        {"C": "A", "V": 20},
        {"C": "B", "V": 5},
        {"C": "B", "V": None},  # unparseable/missing measures are skipped
    ]
    dim = {"name": "C", "field_role": "dimension"}
    meas = {"name": "V", "field_role": "measure"}
    pairs, total = _series(rows, "avg", dim, meas)
    assert pairs == [("A", 15.0), ("B", 5.0)] and total == 2


# --------------------------------------------------------------------------- gate + errors


def test_data_disabled_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.dashboard_items.ENABLE_INAPI_EGRESS", False)
    assert _data(client, admin_headers, "whatever").status_code == 503


def test_data_missing_item_returns_404(client, admin_headers, monkeypatch):
    _enable_data(monkeypatch)
    assert _data(client, admin_headers, "no-such-id").status_code == 404


def test_data_requires_auth(client, monkeypatch):
    _enable_data(monkeypatch)
    assert client.get("/api/dashboard-items/x/data").status_code in (401, 403)


# --------------------------------------------------------------------------- aggregations


def test_count_by_dimension_series(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    _enable_data(monkeypatch)

    r = _data(client, admin_headers, item["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aggregation"] == "count" and body["dimension"] == "ShipCountry"
    assert body["sample_size"] == 10
    # biggest bucket first; UK/France tie broken by label (France < UK)
    assert body["series"] == [
        {"label": "USA", "value": 4},
        {"label": "France", "value": 3},
        {"label": "UK", "value": 3},
    ]
    assert body["buckets_total"] == 3 and body["truncated"] is False


def test_sum_by_dimension_series(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Freight by ShipCountry")
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    assert body["aggregation"] == "sum" and body["measure"] == "Freight"
    assert body["series"] == [
        {"label": "USA", "value": 58.0},
        {"label": "France", "value": 45.0},
        {"label": "UK", "value": 42.0},
    ]


def test_kpi_without_fields_counts_rows(client, admin_headers, monkeypatch):
    """'Total Orders' has NO suggestion_fields — the dataset resolves via the suggestion."""
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Total Orders")
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    assert body["dimension"] is None
    assert body["series"] == [{"label": "Total Orders", "value": 10}]


def test_kpi_sum_over_measure(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Total Freight")
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    assert body["series"] == [{"label": "Total Freight", "value": 145.0}]


def test_temporal_series_sorts_by_label(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Freight over OrderDate")
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    # single date in the fixture -> one chronological bucket summing all freight
    assert body["series"] == [{"label": "1998-05-01T00:00:00Z", "value": 145.0}]


# --------------------------------------------------------------------------- governance


def test_pii_flagged_dimension_is_withheld(client, admin_headers, monkeypatch):
    from app.db.connection import get_cursor

    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    ds = _dataset_id(sid)
    fid = _field_id(ds, "ShipCountry")
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO pii_flags (id, name, dataset_id, discovered_field_id, category, "
            "status, detection_tier) "
            "VALUES (%s, 'flag', %s, %s, 'other', 'flagged', 'schema')",
            (uuid.uuid4().hex, ds, fid),
        )
    _enable_data(monkeypatch)

    r = _data(client, admin_headers, item["id"])
    assert r.status_code == 422
    assert "ShipCountry" in r.json()["detail"]


def test_confirmed_flag_withholds_dismissed_does_not(
    client, admin_headers, monkeypatch
):
    """'confirmed' is an ACTIVE flag (withholds); a 'dismissed' flag must NOT block the
    chart — the reviewer decided the field is not personal data."""
    from app.db.connection import get_cursor

    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    ds = _dataset_id(sid)
    fid = _field_id(ds, "ShipCountry")
    _enable_data(monkeypatch)

    flag_id = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO pii_flags (id, name, dataset_id, discovered_field_id, category, "
            "status, detection_tier) "
            "VALUES (%s, 'flag', %s, %s, 'other', 'confirmed', 'schema')",
            (flag_id, ds, fid),
        )
    assert _data(client, admin_headers, item["id"]).status_code == 422

    with get_cursor() as cur:
        cur.execute(
            "UPDATE pii_flags SET status = 'dismissed' WHERE id = %s", (flag_id,)
        )
    assert _data(client, admin_headers, item["id"]).status_code == 200


def test_suppressed_subject_dropped_from_series(client, admin_headers, monkeypatch):
    """Erase OrderID 0 (a USA row): USA drops 4 -> 3 and the totals shrink with it —
    charts are value-level output, so counts exclude the erased subject too. The response
    must NOT telegraph the erasure: sample_size is post-suppression and there is no
    pre/post pair to diff."""
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    ds = _dataset_id(sid)
    _suppress(ds, _business_key_of(ds, _ROWS[0]))
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    assert body["sample_size"] == 9  # the erased subject is invisible, not redacted
    assert "rows_used" not in body  # no pre/post pair = no erasure telegraph
    assert body["series"] == [
        {"label": "France", "value": 3},
        {"label": "UK", "value": 3},
        {"label": "USA", "value": 3},
    ]


def test_suppressed_subject_dropped_from_sums(client, admin_headers, monkeypatch):
    """Same erasure, sum aggregation: OrderID 0 carries Freight 10.0 -> USA 58 becomes 48."""
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Freight by ShipCountry")
    ds = _dataset_id(sid)
    _suppress(ds, _business_key_of(ds, _ROWS[0]))
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    assert body["series"] == [
        {"label": "USA", "value": 48.0},
        {"label": "France", "value": 45.0},
        {"label": "UK", "value": 42.0},
    ]


def test_suppressed_subject_dropped_from_fieldless_kpi(
    client, admin_headers, monkeypatch
):
    """'Total Orders' resolves its dataset via the suggestion (no fields) — suppression
    must still apply on that path: 10 rows count as 9."""
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Total Orders")
    ds = _dataset_id(sid)
    _suppress(ds, _business_key_of(ds, _ROWS[0]))
    _enable_data(monkeypatch)

    body = _data(client, admin_headers, item["id"]).json()
    assert body["series"] == [{"label": "Total Orders", "value": 9}]
    assert body["sample_size"] == 9


def test_suppression_fails_closed_without_pepper(client, admin_headers, monkeypatch):
    """Entries exist but the pepper is missing: the service raises rather than serving the
    erased subject (same contract as profiling)."""
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    ds = _dataset_id(sid)
    _suppress(ds, _business_key_of(ds, _ROWS[0]))
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER")
    monkeypatch.setattr(
        "app.dashboard.data_service._fetch_rows", lambda url: _ROWS_JSON
    )
    from app.dashboard.data_service import item_data

    with pytest.raises(RuntimeError, match="AIDW_SUPPRESSION_PEPPER"):
        item_data(item["id"])


def test_no_pepper_needed_when_nothing_suppressed(client, admin_headers, monkeypatch):
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER", raising=False)
    sid = _discover(client, admin_headers, monkeypatch)
    item = _accept(client, admin_headers, sid, "Orders by ShipCountry")
    _enable_data(monkeypatch)

    r = _data(client, admin_headers, item["id"])
    assert r.status_code == 200  # lazy skip: hashing never runs without entries
    assert r.json()["sample_size"] == 10
