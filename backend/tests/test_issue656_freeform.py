"""Issue #656 freeform proof — one test, stubbed $metadata with five entity sets, real Postgres.

Proves, in a single test:
* a no-body discovery is unchanged: all five sets are discovered and created (AC-1, AC-3);
* discovering two named sets on a fresh source creates exactly two datasets with their fields,
  and the response counts report only the requested subset (AC-1, AC-3, AC-5);
* a requested name absent from the $metadata raises ValueError naming every missing name and
  writes nothing (AC-1, AC-3);
* the API returns 422 for missing names (detail names every missing one) and for an empty list,
  without creating or updating any datasets/discovered_fields rows (AC-2, AC-4);
* malformed JSON and non-string entity_sets keep FastAPI's standard validation 422 envelope
  (AC-2).
"""

import time

import pytest

from app.discovery.service import discover_source

_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NW656" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Alpha">
        <Key><PropertyRef Name="AlphaID"/></Key>
        <Property Name="AlphaID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
      </EntityType>
      <EntityType Name="Beta">
        <Key><PropertyRef Name="BetaID"/></Key>
        <Property Name="BetaID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Code" Type="Edm.String" Nullable="false"/>
        <Property Name="Score" Type="Edm.Decimal"/>
      </EntityType>
      <EntityType Name="Gamma">
        <Key><PropertyRef Name="GammaID"/></Key>
        <Property Name="GammaID" Type="Edm.Int32" Nullable="false"/>
      </EntityType>
      <EntityType Name="Delta">
        <Key><PropertyRef Name="DeltaID"/></Key>
        <Property Name="DeltaID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="X" Type="Edm.String"/>
        <Property Name="Y" Type="Edm.Int32"/>
        <Property Name="Z" Type="Edm.Decimal"/>
      </EntityType>
      <EntityType Name="Epsilon">
        <Key><PropertyRef Name="EpsilonID"/></Key>
        <Property Name="EpsilonID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Label" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Alpha" EntityType="NW656.Alpha"/>
        <EntitySet Name="Beta" EntityType="NW656.Beta"/>
        <EntitySet Name="Gamma" EntityType="NW656.Gamma"/>
        <EntitySet Name="Delta" EntityType="NW656.Delta"/>
        <EntitySet Name="Epsilon" EntityType="NW656.Epsilon"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

# The five entity sets and their fields, as the stubbed $metadata defines them.
SETS = {
    "Alpha": ("AlphaID", "Name"),
    "Beta": ("BetaID", "Code", "Score"),
    "Gamma": ("GammaID",),
    "Delta": ("DeltaID", "X", "Y", "Z"),
    "Epsilon": ("EpsilonID", "Label"),
}
TOTAL_FIELDS = sum(len(fields) for fields in SETS.values())  # 12


def _make_odata_source(client, admin_headers):
    sid = client.post(
        "/api/sources", json={"name": "nw656", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    r1 = client.post(
        "/api/source-connections",
        json={
            "name": "conn",
            "endpoint": "https://svc.example/odata",
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
            "default_entity_set": "Alpha",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    assert r2.status_code == 201, r2.text
    return sid


def _datasets_for(client, admin_headers, source_id):
    return [
        d
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d.get("source_id") == source_id
    ]


def _fields_for(client, admin_headers, source_id):
    ds_ids = {d["id"] for d in _datasets_for(client, admin_headers, source_id)}
    return [
        f
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f.get("dataset_id") in ds_ids
    ]


def test_issue656_freeform(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _EDMX)

    # AC-1/AC-3: no body keeps today's behaviour — all five sets are discovered and created.
    sid_a = _make_odata_source(client, admin_headers)
    r = client.post(f"/api/sources/{sid_a}/discover", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["datasets_discovered"] == 5
    assert body["fields_discovered"] == TOTAL_FIELDS
    assert body["datasets_created"] == 5
    assert body["fields_created"] == TOTAL_FIELDS
    assert {d["name"] for d in _datasets_for(client, admin_headers, sid_a)} == set(SETS)
    assert len(_fields_for(client, admin_headers, sid_a)) == TOTAL_FIELDS

    # AC-1/AC-3/AC-5: two named sets on a fresh source create exactly two datasets with their
    # fields; the response counts report only the requested subset, not the full metadata.
    sid_b = _make_odata_source(client, admin_headers)
    r = client.post(
        f"/api/sources/{sid_b}/discover",
        json={"entity_sets": ["Beta", "Epsilon"]},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["datasets_discovered"] == 2
    assert body["fields_discovered"] == len(SETS["Beta"]) + len(SETS["Epsilon"])
    assert body["datasets_created"] == 2
    assert body["fields_created"] == len(SETS["Beta"]) + len(SETS["Epsilon"])
    datasets = _datasets_for(client, admin_headers, sid_b)
    assert {d["name"] for d in datasets} == {"Beta", "Epsilon"}
    ds_id_by_name = {d["name"]: d["id"] for d in datasets}
    fields = _fields_for(client, admin_headers, sid_b)
    fields_by_set = {
        ds: sorted(f["name"] for f in fields if f["dataset_id"] == ds_id)
        for ds, ds_id in ds_id_by_name.items()
    }
    assert fields_by_set == {
        "Beta": sorted(SETS["Beta"]),
        "Epsilon": sorted(SETS["Epsilon"]),
    }

    # AC-2/AC-4: missing names -> 422 naming every missing name, and no datasets or
    # discovered_fields rows are created or updated (updated_at would move).
    before_datasets = _datasets_for(client, admin_headers, sid_b)
    before_fields = _fields_for(client, admin_headers, sid_b)
    time.sleep(0.01)
    r = client.post(
        f"/api/sources/{sid_b}/discover",
        json={"entity_sets": ["Beta", "Nope", "AlsoMissing"]},
        headers=admin_headers,
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str)
    assert "Nope" in detail and "AlsoMissing" in detail
    assert _datasets_for(client, admin_headers, sid_b) == before_datasets
    assert _fields_for(client, admin_headers, sid_b) == before_fields

    # AC-1/AC-3: at the service level, a missing name raises ValueError naming every missing
    # name and writes nothing (fresh source C has no rows at all).
    sid_c = _make_odata_source(client, admin_headers)
    with pytest.raises(ValueError) as excinfo:
        discover_source(sid_c, ["GhostOne", "GhostTwo"])
    message = str(excinfo.value)
    assert "GhostOne" in message and "GhostTwo" in message
    assert _datasets_for(client, admin_headers, sid_c) == []
    assert _fields_for(client, admin_headers, sid_c) == []

    # AC-2: an empty list is a 422; malformed JSON and non-string entity_sets keep FastAPI's
    # standard validation 422 envelope.
    r = client.post(
        f"/api/sources/{sid_b}/discover",
        json={"entity_sets": []},
        headers=admin_headers,
    )
    assert r.status_code == 422

    r = client.post(
        f"/api/sources/{sid_b}/discover",
        json={"entity_sets": [1, "Beta"]},
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Request validation failed."
    assert r.json()["errors"]

    r = client.post(
        f"/api/sources/{sid_b}/discover",
        json={"entity_sets": "Beta"},
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Request validation failed."
    assert r.json()["errors"]

    r = client.post(
        f"/api/sources/{sid_b}/discover",
        content=b'{"entity_sets": ',
        headers={**admin_headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Request validation failed."
    assert r.json()["errors"]
