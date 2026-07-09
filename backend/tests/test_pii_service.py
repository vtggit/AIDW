"""PII reconciler + retro-scrub tests (real Postgres): schema-tier scan writes pii_flags bound
to real discovered fields, retro-scrub NULLs leaked profile values with an audit row, the scan
is idempotent + bidirectional (stale/revive), human decisions are sticky, and a schema scan
never stales a profile-tier flag (the ratchet)."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.pii.service import reconcile_flags_for_dataset, scan_pii_for_source

_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Demo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Customer">
        <Key><PropertyRef Name="CustomerID"/></Key>
        <Property Name="CustomerID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="EmailAddress" Type="Edm.String"/>
        <Property Name="PhoneNumber" Type="Edm.String"/>
        <Property Name="Region" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Customers" EntityType="Demo.Customer"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


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


def _flags_for_source(client, admin_headers, sid):
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


# ── schema-tier scan writes flags bound to real fields ──────────────────────


def test_discovery_triggers_pii_scan_with_bound_flags(
    client, admin_headers, monkeypatch
):
    sid = _make_source(client, admin_headers)
    body = _discover(client, admin_headers, monkeypatch, sid)
    # the scan ran as an automatic discovery trigger and reported its counts
    assert body["pii_flags_created"] == 3  # CustomerID, EmailAddress, PhoneNumber

    flags = {f["category"]: f for f in _flags_for_source(client, admin_headers, sid)}
    by_field = {
        f["discovered_field_id"]: f
        for f in _flags_for_source(client, admin_headers, sid)
    }
    assert set(flags) == {"direct_identifier", "contact"}
    # every flag binds to a REAL discovered field (observable output state)
    email_id = _field_id(client, admin_headers, "EmailAddress")
    key_id = _field_id(client, admin_headers, "CustomerID")
    assert by_field[email_id]["category"] == "contact"
    assert by_field[key_id]["category"] == "direct_identifier"
    assert all(f["status"] == "flagged" for f in by_field.values())
    # Region is not PII — no flag
    region_id = _field_id(client, admin_headers, "Region")
    assert region_id not in by_field


# ── retro-scrub closes the leak ─────────────────────────────────────────────


def _insert_profile(cur, field_id, now):
    cur.execute(
        "INSERT INTO field_profiles (id, name, discovered_field_id, row_count, null_count, "
        "distinct_count, min_value, max_value, most_common_value, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            str(uuid4()),
            "p",
            field_id,
            10,
            0,
            9,
            "a@a.com",
            "z@z.com",
            "bob@x.com",
            now,
            now,
        ),
    )


def test_retro_scrub_nulls_leaked_values_and_audits(client, admin_headers, monkeypatch):
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    email_id = _field_id(client, admin_headers, "EmailAddress")

    # simulate a profile written BEFORE the watchdog existed: raw example values at rest
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        _insert_profile(cur, email_id, now)

    # a re-scan retro-scrubs the leaked values (the flag already exists)
    counts = scan_pii_for_source(sid)
    assert counts["profiles_redacted"] >= 1

    with get_cursor() as cur:
        cur.execute(
            "SELECT min_value, max_value, most_common_value, row_count, distinct_count "
            "FROM field_profiles WHERE discovered_field_id = %s",
            (email_id,),
        )
        prof = cur.fetchone()
        # values gone, aggregate counts kept
        assert prof["min_value"] is None and prof["max_value"] is None
        assert prof["most_common_value"] is None
        assert prof["row_count"] == 10 and prof["distinct_count"] == 9
        # an audit row records the redaction WITHOUT the values
        cur.execute(
            "SELECT action, actor_sub, details_json FROM audit_log "
            "WHERE entity_id = %s AND action = 'redact_profile'",
            (email_id,),
        )
        audit = cur.fetchone()
        assert audit is not None and audit["actor_sub"] == "system:pii-watchdog"
        assert "a@a.com" not in (audit["details_json"] or "")

    # idempotent: a second scan re-scrubs nothing (values already gone)
    assert scan_pii_for_source(sid)["profiles_redacted"] == 0


# ── idempotency, stale/revive, stickiness, ratchet ──────────────────────────


def test_rescan_is_idempotent(client, admin_headers, monkeypatch):
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    before = len(_flags_for_source(client, admin_headers, sid))
    scan_pii_for_source(sid)
    assert len(_flags_for_source(client, admin_headers, sid)) == before


def test_dismissed_flag_is_sticky(client, admin_headers, monkeypatch):
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    email_id = _field_id(client, admin_headers, "EmailAddress")
    flag = next(
        f
        for f in _flags_for_source(client, admin_headers, sid)
        if f["discovered_field_id"] == email_id
    )
    # steward dismisses it (via generic CRUD for now)
    client.put(
        f"/api/pii-flags/{flag['id']}",
        json={"status": "dismissed"},
        headers=admin_headers,
    )
    scan_pii_for_source(sid)  # a re-scan must NOT resurrect a dismissed flag
    after = next(
        f
        for f in _flags_for_source(client, admin_headers, sid)
        if f["id"] == flag["id"]
    )
    assert after["status"] == "dismissed"


def test_stale_when_rule_stops_then_revive(client, admin_headers, monkeypatch):
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    ds_id = next(
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    )
    # reconcile a schema-tier set that no longer contains the contact candidates
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name FROM discovered_fields WHERE dataset_id = %s", (ds_id,)
        )
        field_rows = [dict(r) for r in cur.fetchall()]
        reconcile_flags_for_dataset(cur, ds_id, field_rows, [], "schema")
    staled = [
        f
        for f in _flags_for_source(client, admin_headers, sid)
        if f["status"] == "stale"
    ]
    assert len(staled) == 3  # all schema-tier flags staled when no rule fires

    # a re-scan revives them (they were never dismissed)
    scan_pii_for_source(sid)
    assert all(
        f["status"] == "flagged" for f in _flags_for_source(client, admin_headers, sid)
    )


def test_schema_scan_does_not_stale_profile_tier_flag(
    client, admin_headers, monkeypatch
):
    """The ratchet: a schema-tier scan reads no values, so it must never stale a profile-tier
    flag on absence — only a human dismiss releases it."""
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid)
    ds_id = next(
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    )
    region_id = _field_id(client, admin_headers, "Region")
    # inject a profile-tier flag on Region (a schema scan never produces one for it)
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO pii_flags (id, name, dataset_id, discovered_field_id, category, "
            "detection_tier, status, confidence, fingerprint, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, 'profile', 'flagged', %s, %s, %s, %s)",
            (
                str(uuid4()),
                "contact:Region",
                ds_id,
                region_id,
                "contact",
                0.9,
                "profile-fp-region",
                now,
                now,
            ),
        )
    # a leaked profile exists for the profile-flagged field
    with get_cursor() as cur:
        _insert_profile(cur, region_id, now)

    counts = scan_pii_for_source(sid)  # schema scan: Region produces no candidate
    region_flag = next(
        f
        for f in _flags_for_source(client, admin_headers, sid)
        if f["fingerprint"] == "profile-fp-region"
    )
    assert region_flag["status"] == "flagged"  # ratcheted — not staled

    # ...AND its leaked values are still scrubbed — scrub is a property of BEING flagged, not of
    # this schema scan re-detecting it (the flag's fingerprint is absent from the schema fresh set)
    assert counts["profiles_redacted"] >= 1
    with get_cursor() as cur:
        cur.execute(
            "SELECT min_value, most_common_value FROM field_profiles "
            "WHERE discovered_field_id = %s",
            (region_id,),
        )
        prof = cur.fetchone()
        assert prof["min_value"] is None and prof["most_common_value"] is None
