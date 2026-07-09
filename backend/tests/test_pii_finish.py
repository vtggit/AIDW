"""PII watchdog completion (governance #75): the profiling detect-before-write seam, the
confirm/dismiss steward endpoints, and the manual pii-scan endpoint — all against real Postgres.
"""

import json

# a schema with a name-obvious PII field (EmailAddress), a value-only PII field whose NAME says
# nothing (Notes, but full of emails), and a benign field (Widget)
_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Demo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Record">
        <Key><PropertyRef Name="RecordID"/></Key>
        <Property Name="RecordID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="EmailAddress" Type="Edm.String"/>
        <Property Name="Notes" Type="Edm.String"/>
        <Property Name="Widget" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Records" EntityType="Demo.Record"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

_ROWS = [
    {
        "RecordID": i,
        "EmailAddress": f"user{i}@example.com",
        "Notes": f"contact{i}@corp.com",  # value-only PII: the NAME is innocuous
        "Widget": f"blue-{i}",
    }
    for i in range(10)
]
_ROWS_JSON = json.dumps({"value": _ROWS}).encode()


def _make_source(client, admin_headers):
    sid = client.post(
        "/api/sources", json={"name": "nw", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={"name": "c", "endpoint": "https://svc.example/odata", "source_id": sid},
        headers=admin_headers,
    )
    return sid


def _discover(client, admin_headers, monkeypatch, sid):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _EDMX)
    return client.post(f"/api/sources/{sid}/discover", headers=admin_headers).json()


def _profile(client, admin_headers, monkeypatch, sid):
    monkeypatch.setattr("app.api.profiling.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _ROWS_JSON)
    return client.post(f"/api/sources/{sid}/profile", headers=admin_headers).json()


def _flags(client, admin_headers, sid):
    ds_ids = {
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    }
    return [
        f
        for f in client.get("/api/pii-flags", headers=admin_headers).json()
        if f.get("dataset_id") in ds_ids
    ]


def _field_id(client, admin_headers, name):
    return next(
        f["id"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["name"] == name
    )


def _profile_row(client, admin_headers, field_id):
    return next(
        (
            p
            for p in client.get("/api/field-profiles", headers=admin_headers).json()
            if p.get("discovered_field_id") == field_id
        ),
        None,
    )


# ── profiling seam: value detection + detect-before-write suppression ────────


def test_profile_flags_value_only_pii_and_suppresses_writes(
    client, admin_headers, monkeypatch
):
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    # after discovery: EmailAddress is name-flagged (schema tier); Notes is NOT
    email_id = _field_id(client, admin_headers, "EmailAddress")
    notes_id = _field_id(client, admin_headers, "Notes")
    widget_id = _field_id(client, admin_headers, "Widget")
    schema_flags = {
        f["discovered_field_id"] for f in _flags(client, admin_headers, sid)
    }
    assert email_id in schema_flags and notes_id not in schema_flags

    body = _profile(client, admin_headers, monkeypatch, sid)
    assert body["fields_profiled"] == 4
    # Notes is 100% emails -> profile-tier flag created despite the innocuous name
    flags = {f["discovered_field_id"]: f for f in _flags(client, admin_headers, sid)}
    assert notes_id in flags and flags[notes_id]["category"] == "contact"
    assert flags[notes_id]["detection_tier"] == "profile"
    # EmailAddress's schema flag was upgraded to profile tier by the value evidence
    assert flags[email_id]["detection_tier"] == "profile"

    # detect-before-write: the flagged fields' profiles landed with NULL example values...
    email_prof = _profile_row(client, admin_headers, email_id)
    notes_prof = _profile_row(client, admin_headers, notes_id)
    assert email_prof["min_value"] is None and email_prof["most_common_value"] is None
    assert notes_prof["min_value"] is None and notes_prof["max_value"] is None
    # ...but the aggregate counts persist (statistics, not values)
    assert email_prof["row_count"] == 10 and email_prof["distinct_count"] == 10
    # ...and a benign field keeps its example values
    widget_prof = _profile_row(client, admin_headers, widget_id)
    assert widget_prof["min_value"] is not None


# ── confirm / dismiss steward endpoints ─────────────────────────────────────


def _a_flag(client, admin_headers, monkeypatch):
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    return sid, _flags(client, admin_headers, sid)[0]


def test_confirm_sets_status_and_audits(client, admin_headers, monkeypatch):
    sid, flag = _a_flag(client, admin_headers, monkeypatch)
    r = client.post(f"/api/pii-flags/{flag['id']}/confirm", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    # audit trail written (the audit table's first real writer)
    audit = client.get("/api/audit?entity_type=pii_flag", headers=admin_headers).json()
    assert any(e["entity_id"] == flag["id"] and e["action"] == "confirm" for e in audit)


def test_dismiss_sets_status_and_audits(client, admin_headers, monkeypatch):
    sid, flag = _a_flag(client, admin_headers, monkeypatch)
    r = client.post(f"/api/pii-flags/{flag['id']}/dismiss", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    audit = client.get("/api/audit?entity_type=pii_flag", headers=admin_headers).json()
    assert any(e["entity_id"] == flag["id"] and e["action"] == "dismiss" for e in audit)


def test_confirm_dismiss_require_admin_and_404(client, admin_headers, user_headers):
    assert (
        client.post("/api/pii-flags/x/confirm", headers=user_headers).status_code == 403
    )
    assert (
        client.post("/api/pii-flags/x/dismiss", headers=user_headers).status_code == 403
    )
    assert (
        client.post("/api/pii-flags/no-such/confirm", headers=admin_headers).status_code
        == 404
    )


def test_dismissed_flag_lifts_suppression_next_profile(
    client, admin_headers, monkeypatch
):
    """After a steward dismisses a false positive, the next profile pass writes real example
    values again (the field no longer carries an active flag)."""
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    notes_id = _field_id(client, admin_headers, "Notes")
    _profile(client, admin_headers, monkeypatch, sid)  # Notes gets a profile-tier flag
    notes_flag = next(
        f
        for f in _flags(client, admin_headers, sid)
        if f["discovered_field_id"] == notes_id
    )
    assert (
        _profile_row(client, admin_headers, notes_id)["min_value"] is None
    )  # suppressed

    client.post(f"/api/pii-flags/{notes_flag['id']}/dismiss", headers=admin_headers)
    _profile(client, admin_headers, monkeypatch, sid)  # re-profile: suppression lifts
    assert _profile_row(client, admin_headers, notes_id)["min_value"] is not None


# ── manual pii-scan endpoint ────────────────────────────────────────────────


def test_pii_scan_endpoint_admin_only(client, admin_headers, user_headers, monkeypatch):
    assert (
        client.post("/api/sources/x/pii-scan", headers=user_headers).status_code == 403
    )
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    # a manual scan re-runs the schema tier and reports counts (no egress, no 503 gate)
    r = client.post(f"/api/sources/{sid}/pii-scan", headers=admin_headers)
    assert r.status_code == 200
    assert "pii_flags_created" in r.json() and "profiles_redacted" in r.json()
