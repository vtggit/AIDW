"""Schema-discovery tests: the deterministic OData reader (checked-in EDMX) and the discover
endpoint (mocked egress, real Postgres). Live V2/V3/V4 fidelity is proven out-of-band.
"""

from app.discovery.schema_reader import ODataSchemaReader

_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Demo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Product">
        <Key><PropertyRef Name="ProductID"/></Key>
        <Property Name="ProductID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
        <Property Name="Price" Type="Edm.Decimal" Nullable="false"/>
      </EntityType>
      <EntityType Name="Category">
        <Key><PropertyRef Name="CategoryID"/></Key>
        <Property Name="CategoryID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Products" EntityType="Demo.Product"/>
        <EntitySet Name="Categories" EntityType="Demo.Category"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


def test_odata_reader_parses_entitysets_keys_and_nullable():
    by = {d.name: d for d in ODataSchemaReader().read(_EDMX)}
    assert set(by) == {"Products", "Categories"}
    prod = by["Products"]
    assert [f.name for f in prod.fields] == ["ProductID", "Name", "Price"]
    assert [f.name for f in prod.fields if f.is_key] == ["ProductID"]
    pid = next(f for f in prod.fields if f.name == "ProductID")
    assert pid.is_key and pid.nullable is False and pid.data_type == "Edm.Int32"
    name = next(f for f in prod.fields if f.name == "Name")
    assert name.nullable is True and not name.is_key


def _make_odata_source(client, admin_headers, endpoint="https://svc.example/odata"):
    sid = client.post(
        "/api/sources", json={"name": "nw", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    r1 = client.post(
        "/api/source-connections",
        json={
            "name": "conn",
            "endpoint": endpoint,
            "protocol_version": "V4",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        "/api/odata-service-configs",
        json={
            "name": "cfg",
            "metadata_path": "$metadata",
            "default_entity_set": "Products",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    assert r2.status_code == 201, r2.text
    return sid


def test_discover_requires_admin(client, user_headers):
    assert (
        client.post("/api/sources/x/discover", headers=user_headers).status_code == 403
    )


def test_discover_disabled_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", False)
    sid = _make_odata_source(client, admin_headers)
    assert (
        client.post("/api/sources/%s/discover" % sid, headers=admin_headers).status_code
        == 503
    )


def test_discover_missing_source_returns_404(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _EDMX)
    assert (
        client.post(
            "/api/sources/no-such-id/discover", headers=admin_headers
        ).status_code
        == 404
    )


def test_discover_populates_datasets_and_fields_with_lineage(
    client, admin_headers, monkeypatch
):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _EDMX)
    sid = _make_odata_source(client, admin_headers)

    r = client.post("/api/sources/%s/discover" % sid, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["datasets_discovered"] == 2 and body["fields_discovered"] == 5
    assert body["datasets_created"] == 2 and body["fields_created"] == 5

    datasets = [
        d
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    ]
    assert {d["name"] for d in datasets} == {"Products", "Categories"}
    ds_ids = {d["id"] for d in datasets}
    fields = [
        f
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f.get("dataset_id") in ds_ids
    ]
    assert len(fields) == 5  # lineage: every discovered field links to a dataset

    # idempotent re-discovery: nothing new created the second time
    again = client.post("/api/sources/%s/discover" % sid, headers=admin_headers).json()
    assert again["datasets_created"] == 0 and again["fields_created"] == 0
