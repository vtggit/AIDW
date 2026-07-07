"""Accept / dismiss + dashboard tests.

A schema-tier suggestion becomes a dashboard item via POST /accept: a 1:1 copy
(title/item_type/aggregation) whose fields are REAL discovered_field references copied from the
suggestion (observable output state), idempotent per suggestion. Dismiss is sticky — the reconciler
never resurrects a dismissed suggestion on re-discovery.
"""

from app.dashboard.service import DEFAULT_DASHBOARD_NAME

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


def _pick(client, admin_headers, sid, title):
    return next(
        s
        for s in _suggestions_for_source(client, admin_headers, sid)
        if s["title"] == title
    )


def test_accept_copies_suggestion_into_dashboard_item_with_real_fields(
    client, admin_headers, monkeypatch
):
    sid = _discover(client, admin_headers, monkeypatch)
    sug = _pick(client, admin_headers, sid, "Orders by ShipCountry")

    r = client.post(f"/api/suggestions/{sug['id']}/accept", headers=admin_headers)
    assert r.status_code == 200, r.text
    item = r.json()

    # 1:1 copy of the suggestion's shape
    assert item["title"] == "Orders by ShipCountry"
    assert item["item_type"] == sug["item_type"] == "bar"
    assert item["aggregation"] == sug["aggregation"] == "count"
    assert item["source_suggestion_id"] == sug["id"]
    assert isinstance(item["position"], int) and item["position"] >= 1

    # the suggestion is now accepted
    accepted = _pick(client, admin_headers, sid, "Orders by ShipCountry")
    assert accepted["status"] == "accepted"

    # the item's field bindings are REAL discovered_field references copied from the suggestion
    sug_field = next(
        sf
        for sf in client.get("/api/suggestion-fields", headers=admin_headers).json()
        if sf.get("suggestion_id") == sug["id"]
    )
    item_fields = [
        f
        for f in client.get("/api/dashboard-item-fields", headers=admin_headers).json()
        if f.get("dashboard_item_id") == item["id"]
    ]
    assert len(item_fields) == 1
    assert item_fields[0]["field_role"] == "dimension"
    assert item_fields[0]["discovered_field_id"] == sug_field["discovered_field_id"]

    # landed on the auto-created default dashboard
    dash = next(
        d
        for d in client.get("/api/dashboards", headers=admin_headers).json()
        if d["id"] == item["dashboard_id"]
    )
    assert dash["name"] == DEFAULT_DASHBOARD_NAME


def test_accept_is_idempotent(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    sug = _pick(client, admin_headers, sid, "Total Orders")

    first = client.post(
        f"/api/suggestions/{sug['id']}/accept", headers=admin_headers
    ).json()
    second = client.post(
        f"/api/suggestions/{sug['id']}/accept", headers=admin_headers
    ).json()
    assert first["id"] == second["id"]  # same item returned, not a duplicate

    items = [
        i
        for i in client.get("/api/dashboard-items", headers=admin_headers).json()
        if i.get("source_suggestion_id") == sug["id"]
    ]
    assert len(items) == 1


def test_accept_into_explicit_dashboard(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    dash = client.post(
        "/api/dashboards", json={"name": "My Board"}, headers=admin_headers
    ).json()
    sug = _pick(client, admin_headers, sid, "Total Orders")

    item = client.post(
        f"/api/suggestions/{sug['id']}/accept?dashboard_id={dash['id']}",
        headers=admin_headers,
    ).json()
    assert item["dashboard_id"] == dash["id"]


def test_accept_missing_suggestion_returns_404(client, admin_headers):
    assert (
        client.post(
            "/api/suggestions/no-such-id/accept", headers=admin_headers
        ).status_code
        == 404
    )


def test_dismiss_is_sticky_across_rediscovery(client, admin_headers, monkeypatch):
    sid = _discover(client, admin_headers, monkeypatch)
    sug = _pick(client, admin_headers, sid, "Orders by ShipCountry")

    r = client.post(f"/api/suggestions/{sug['id']}/dismiss", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "dismissed"

    # re-discovery must NOT resurrect a dismissed suggestion (anti-resurrection)
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    still = _pick(client, admin_headers, sid, "Orders by ShipCountry")
    assert still["status"] == "dismissed"
    twins = [
        s
        for s in _suggestions_for_source(client, admin_headers, sid)
        if s["title"] == "Orders by ShipCountry"
    ]
    assert len(twins) == 1  # no duplicate 'suggested' twin created
