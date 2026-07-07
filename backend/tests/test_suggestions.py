"""Schema-tier dashboard-suggestion tests.

Two layers:
  * the pure engine (no DB) — asserts the value-probe findings: semantic rules fire and the known
    noise sources (summing prices, bar-by-identifier) are suppressed;
  * the automatic seam through the discover endpoint (mocked egress, real Postgres) — asserts
    suggestions are generated automatically, reference REAL discovered_field ids (the reward-hack
    guard: observable output state, not "handler ran"), are idempotent, and go stale when the schema
    that produced them disappears.
"""

from app.db.connection import get_cursor
from app.suggestion.engine import generate_suggestions
from app.suggestion.service import regenerate_suggestions_for_source


def _field(name, data_type, key=False, nullable=True, pos=0):
    return {
        "name": name,
        "data_type": data_type,
        "is_key": key,
        "is_nullable": nullable,
        "field_position": pos,
    }


_ORDERS = [
    _field("OrderID", "Edm.Int32", key=True, nullable=False, pos=0),
    _field("OrderDate", "Edm.DateTimeOffset", pos=1),
    _field("Freight", "Edm.Decimal", pos=2),
    _field("ShipCountry", "Edm.String", pos=3),
    _field("UnitPrice", "Edm.Decimal", pos=4),
    _field("CompanyName", "Edm.String", pos=5),
]


# --------------------------------------------------------------------------- engine (pure)


def test_engine_semantic_rules_fire():
    titles = {c.title for c in generate_suggestions("Orders", _ORDERS)}
    assert "Freight over OrderDate" in titles  # temporal + measure -> line
    assert "Orders by ShipCountry" in titles  # name-categorical dimension -> bar
    assert "Freight by ShipCountry" in titles  # measure by dimension -> bar/sum
    assert "Total Freight" in titles  # additive measure -> KPI
    assert "Total Orders" in titles  # row-count KPI


def test_engine_suppresses_known_noise():
    cands = generate_suggestions("Orders", _ORDERS)
    titles = {c.title for c in cands}
    assert "Total UnitPrice" not in titles  # price is non-additive: never summed
    assert "Orders by CompanyName" not in titles  # identifier-ish name: not a dimension
    # no aggregation anywhere sums a non-additive field
    for c in cands:
        for f in c.fields:
            assert not (c.aggregation == "sum" and f.field_name == "UnitPrice")


def test_engine_line_binds_temporal_and_measure():
    line = next(
        c for c in generate_suggestions("Orders", _ORDERS) if c.item_type == "line"
    )
    assert {f.role: f.field_name for f in line.fields} == {
        "temporal": "OrderDate",
        "measure": "Freight",
    }
    assert line.aggregation == "sum" and line.strategy == "schema-only"


def test_engine_is_deterministic():
    a = generate_suggestions("Orders", _ORDERS)
    b = generate_suggestions("Orders", _ORDERS)
    assert [c.fingerprint for c in a] == [c.fingerprint for c in b]
    # every candidate in one dataset has a distinct fingerprint (its per-dataset idempotency key)
    assert len({c.fingerprint for c in a}) == len(a)


def test_engine_no_measure_no_temporal_line_and_no_bar_without_dimension():
    # a dataset with only a key + a plain name: only the generic rules fire
    fields = [
        _field("Id", "Edm.Int32", key=True, pos=0),
        _field("Label", "Edm.String", pos=1),
    ]
    cands = generate_suggestions("Things", fields)
    types = {c.item_type for c in cands}
    assert "line" not in types  # no measure + temporal
    assert "bar" not in types  # "Label" is not a good dimension name
    assert {c.title for c in cands} >= {"Total Things", "Things details"}


def test_engine_identifier_numerics_are_not_summed():
    # 'count' must match as a whole token, not a substring: AccountId/CountryCode are identifiers,
    # never measures; OrderCount is a real additive measure.
    fields = [
        _field("AccountId", "Edm.Int64", pos=0),
        _field("CountryCode", "Edm.Int32", pos=1),
        _field("OrderCount", "Edm.Int32", pos=2),
    ]
    titles = {c.title for c in generate_suggestions("Rows", fields)}
    assert "Total AccountId" not in titles  # 'Ac-count-Id' is not a measure
    assert "Total CountryCode" not in titles  # 'Count-ry Code' identifier suffix
    assert "Total OrderCount" in titles  # 'count' as a whole token is additive


# --------------------------------------------------------------------------- seam (integration)

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
      <EntityType Name="Customer">
        <Key><PropertyRef Name="CustomerID"/></Key>
        <Property Name="CustomerID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="CompanyName" Type="Edm.String"/>
        <Property Name="Country" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Orders" EntityType="NW.Order"/>
        <EntitySet Name="Customers" EntityType="NW.Customer"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


def _make_odata_source(client, admin_headers, endpoint="https://svc.example/odata"):
    sid = client.post(
        "/api/sources", json={"name": "nw", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    assert (
        client.post(
            "/api/source-connections",
            json={
                "name": "conn",
                "endpoint": endpoint,
                "protocol_version": "V4",
                "source_id": sid,
            },
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/odata-service-configs",
            json={
                "name": "cfg",
                "metadata_path": "$metadata",
                "default_entity_set": "Orders",
                "source_id": sid,
            },
            headers=admin_headers,
        ).status_code
        == 201
    )
    return sid


def _enable_discovery(monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _RICH_EDMX)


def _source_dataset_ids(client, admin_headers, sid):
    return {
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    }


def _suggestions_for_source(client, admin_headers, sid):
    ds_ids = _source_dataset_ids(client, admin_headers, sid)
    return [
        s
        for s in client.get("/api/suggestions", headers=admin_headers).json()
        if s.get("dataset_id") in ds_ids
    ]


def _source_field_id(client, admin_headers, sid, field_name):
    """The discovered_field id of `field_name` WITHIN this source's datasets. Filtering by source is
    essential: application tables accumulate across tests, so other sources have same-named fields.
    """
    ds_ids = _source_dataset_ids(client, admin_headers, sid)
    return next(
        f["id"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["name"] == field_name and f.get("dataset_id") in ds_ids
    )


def test_discovery_generates_suggestions_referencing_real_fields(
    client, admin_headers, monkeypatch
):
    _enable_discovery(monkeypatch)
    sid = _make_odata_source(client, admin_headers)

    body = client.post(f"/api/sources/{sid}/discover", headers=admin_headers).json()
    assert body["datasets_discovered"] == 2 and body["fields_discovered"] == 8
    # Orders: 6 (rowcount, total-freight, freight-over-date, by-country, freight-by-country, table)
    # Customers: 3 (rowcount, by-country, table)
    assert body["suggestions_created"] == 9

    suggestions = _suggestions_for_source(client, admin_headers, sid)
    titles = {s["title"] for s in suggestions}
    assert {
        "Freight over OrderDate",
        "Orders by ShipCountry",
        "Freight by ShipCountry",
        "Customers by Country",
    } <= titles
    assert "Customers by CompanyName" not in titles  # noise suppressed end-to-end

    # observable output state: the "Orders by ShipCountry" suggestion's dimension field is a REAL
    # discovered_fields id, not free text.
    by_country = next(s for s in suggestions if s["title"] == "Orders by ShipCountry")
    ship_country_field_id = _source_field_id(client, admin_headers, sid, "ShipCountry")
    links = [
        sf
        for sf in client.get("/api/suggestion-fields", headers=admin_headers).json()
        if sf.get("suggestion_id") == by_country["id"]
    ]
    assert len(links) == 1
    assert links[0]["field_role"] == "dimension"
    assert links[0]["discovered_field_id"] == ship_country_field_id


def test_discovery_suggestions_are_idempotent(client, admin_headers, monkeypatch):
    _enable_discovery(monkeypatch)
    sid = _make_odata_source(client, admin_headers)

    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    before = len(_suggestions_for_source(client, admin_headers, sid))
    again = client.post(f"/api/sources/{sid}/discover", headers=admin_headers).json()
    assert (
        again["suggestions_created"] == 0
    )  # anti-resurrection: same schema, no new rows
    assert len(_suggestions_for_source(client, admin_headers, sid)) == before


def test_suggestion_goes_stale_when_its_field_vanishes(
    client, admin_headers, monkeypatch
):
    _enable_discovery(monkeypatch)
    sid = _make_odata_source(client, admin_headers)
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)

    # simulate the field vanishing upstream (deleted_at is reserved for exactly this)
    ship_country_field_id = _source_field_id(client, admin_headers, sid, "ShipCountry")
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM discovered_fields WHERE id = %s", (ship_country_field_id,)
        )

    result = regenerate_suggestions_for_source(sid)
    assert (
        result["suggestions_staled"] >= 2
    )  # "Orders by ShipCountry" + "Freight by ShipCountry"

    by_status = {
        s["title"]: s["status"]
        for s in _suggestions_for_source(client, admin_headers, sid)
    }
    assert by_status["Orders by ShipCountry"] == "stale"
    assert by_status["Freight by ShipCountry"] == "stale"
    assert (
        by_status["Total Orders"] == "suggested"
    )  # unaffected suggestions stay active
    assert by_status["Freight over OrderDate"] == "suggested"


def test_suggestion_revives_and_rebinds_when_field_returns(
    client, admin_headers, monkeypatch
):
    _enable_discovery(monkeypatch)
    sid = _make_odata_source(client, admin_headers)
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)

    old_id = _source_field_id(client, admin_headers, sid, "ShipCountry")
    with (
        get_cursor() as cur
    ):  # field vanishes -> suggestion goes stale, binding NULLed by the FK
        cur.execute("DELETE FROM discovered_fields WHERE id = %s", (old_id,))
    regenerate_suggestions_for_source(sid)

    # field returns via re-discovery (a NEW discovered_fields id); the seam must revive AND rebind
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    new_id = _source_field_id(client, admin_headers, sid, "ShipCountry")
    assert new_id != old_id

    sug = next(
        s
        for s in _suggestions_for_source(client, admin_headers, sid)
        if s["title"] == "Orders by ShipCountry"
    )
    assert sug["status"] == "suggested"  # revived, not left stale
    links = [
        sf
        for sf in client.get("/api/suggestion-fields", headers=admin_headers).json()
        if sf.get("suggestion_id") == sug["id"]
    ]
    assert len(links) == 1  # old binding replaced, not duplicated
    assert (
        links[0]["discovered_field_id"] == new_id
    )  # rebound to the REAL new id, not left NULL


def test_crud_rejects_out_of_enum_item_type(client, admin_headers):
    # a CHECK violation is a client error: 422, not a 503 "database unavailable"
    r = client.post(
        "/api/suggestions",
        json={"name": "x", "item_type": "scatter"},
        headers=admin_headers,
    )
    assert r.status_code == 422, r.text
