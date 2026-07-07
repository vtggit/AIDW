"""Profile-tier tests: the pure stats + re-score helpers, and the profile endpoint (mocked data
egress, real Postgres) that writes field_profiles and re-scores suggestions with real cardinality.
"""

import json

from app.profiling.service import _stats
from app.suggestion.rescore import profile_score

# --------------------------------------------------------------------------- pure helpers


def test_stats_counts_nulls_and_distinct():
    rows = [{"C": "USA"}, {"C": "UK"}, {"C": "USA"}, {"C": None}, {}]
    st = _stats(rows, "C")
    assert st["row_count"] == 5
    assert st["null_count"] == 2  # explicit None + missing key
    assert st["distinct_count"] == 2  # USA, UK
    assert st["most_common_value"] == "USA"
    assert st["min_value"] == "UK" and st["max_value"] == "USA"


def test_profile_score_dimension_and_measure():
    # confirmed low-arity categorical -> boosted
    assert (
        profile_score(
            0.55,
            [
                {
                    "field_role": "dimension",
                    "row_count": 10,
                    "distinct_count": 3,
                    "null_count": 0,
                }
            ],
        )
        == 0.82
    )
    # near-unique field -> demoted hard
    assert (
        profile_score(
            0.55,
            [
                {
                    "field_role": "dimension",
                    "row_count": 10,
                    "distinct_count": 9,
                    "null_count": 0,
                }
            ],
        )
        == 0.12
    )
    # fully-populated measure -> fill-boosted
    assert (
        profile_score(
            0.50,
            [
                {
                    "field_role": "measure",
                    "row_count": 10,
                    "distinct_count": 8,
                    "null_count": 0,
                }
            ],
        )
        == 0.8
    )
    # nothing data-dependent (row-count KPI / detail table) -> left as-is
    assert profile_score(0.40, []) is None
    assert (
        profile_score(
            0.40,
            [
                {
                    "field_role": "display",
                    "row_count": 10,
                    "distinct_count": 5,
                    "null_count": 0,
                }
            ],
        )
        is None
    )


# --------------------------------------------------------------------------- endpoint (integration)

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

_ROWS = [
    {
        "OrderID": i,
        "OrderDate": "1998-05-01T00:00:00Z",
        "Freight": 10.0 + i,
        "ShipCountry": ["USA", "UK", "France"][
            i % 3
        ],  # 3 distinct over 10 rows -> low arity
        "CustomerID": 100 + i,
    }
    for i in range(10)
]
_ROWS_JSON = json.dumps({"value": _ROWS}).encode()


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


def _discovered(client, admin_headers, monkeypatch):
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


def test_profile_requires_admin(client, user_headers):
    assert (
        client.post("/api/sources/x/profile", headers=user_headers).status_code == 403
    )


def test_profile_disabled_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.profiling.ENABLE_INAPI_EGRESS", False)
    sid = _make_odata_source(client, admin_headers)
    assert (
        client.post(f"/api/sources/{sid}/profile", headers=admin_headers).status_code
        == 503
    )


def test_profile_missing_source_returns_404(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.profiling.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _ROWS_JSON)
    assert (
        client.post(
            "/api/sources/no-such-id/profile", headers=admin_headers
        ).status_code
        == 404
    )


def test_profile_populates_profiles_and_rescores(client, admin_headers, monkeypatch):
    sid = _discovered(client, admin_headers, monkeypatch)
    monkeypatch.setattr("app.api.profiling.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _ROWS_JSON)

    body = client.post(f"/api/sources/{sid}/profile", headers=admin_headers).json()
    assert body["datasets_profiled"] == 1 and body["fields_profiled"] == 5
    # rescored: Total Freight, Freight over OrderDate, Orders by ShipCountry, Freight by ShipCountry
    assert body["suggestions_rescored"] == 4

    # the ShipCountry profile carries real cardinality (3 distinct over 10 sampled rows)
    field_ids = {
        f["id"]: f["name"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["name"] in ("ShipCountry", "Freight")
    }
    profiles = {
        field_ids[p["discovered_field_id"]]: p
        for p in client.get("/api/field-profiles", headers=admin_headers).json()
        if p.get("discovered_field_id") in field_ids
    }
    assert profiles["ShipCountry"]["distinct_count"] == 3
    assert (
        profiles["ShipCountry"]["row_count"] == 10
        and profiles["ShipCountry"]["null_count"] == 0
    )

    by_title = {
        s["title"]: s for s in _suggestions_for_source(client, admin_headers, sid)
    }
    # a confirmed low-arity dimension is boosted and marked profile-tier
    assert by_title["Orders by ShipCountry"]["strategy"] == "profile"
    assert by_title["Orders by ShipCountry"]["score"] == 0.82
    # a fully-populated measure KPI is fill-boosted
    assert by_title["Total Freight"]["strategy"] == "profile"
    assert by_title["Total Freight"]["score"] == 0.8
    # a generic row-count KPI has nothing to profile -> stays schema-tier
    assert by_title["Total Orders"]["strategy"] == "schema-only"

    # idempotent: a second profile updates the same rows, doesn't duplicate
    before = len(client.get("/api/field-profiles", headers=admin_headers).json())
    client.post(f"/api/sources/{sid}/profile", headers=admin_headers)
    assert (
        len(client.get("/api/field-profiles", headers=admin_headers).json()) == before
    )
