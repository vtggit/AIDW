"""Consent flow — flat v1 surface over normalized storage, transactional audit."""

import pytest


def test_contact_consent_flow(client, admin_headers, monkeypatch):
    c = client.post(
        "/api/contacts", json={"name": "Consent Target"}, headers=admin_headers
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    fresh = client.get("/api/contacts/" + cid, headers=admin_headers).json()
    assert fresh["email_consent_status"] == "unknown"  # retroactive default
    bad = client.put(
        "/api/contacts/" + cid,
        json={"email_consent_status": "banana"},
        headers=admin_headers,
    )
    assert bad.status_code == 422 and "email_consent_status" in bad.text
    ok = client.put(
        "/api/contacts/" + cid,
        json={"email_consent_status": "opted_out", "consent_source": "manual"},
        headers=admin_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["email_consent_status"] == "opted_out"
    got = client.get("/api/contacts/" + cid, headers=admin_headers).json()
    assert got["email_consent_status"] == "opted_out"
    assert got["consent_source"] == "manual" and got["consent_updated_at"]
    aud = client.get("/api/audit?entity_type=contact", headers=admin_headers)
    assert aud.status_code == 200, aud.text
    events = [
        e
        for e in aud.json()
        if e["entity_id"] == cid and e["action"] == "consent_change"
    ]
    assert len(events) == 1
    assert events[0]["details"]["old"] == "unknown"
    assert events[0]["details"]["new"] == "opted_out"
    assert events[0]["details"]["source"] == "manual"
    # AC-5: a failed audit write rolls back the consent mutation (one transaction)
    from app.repositories.contact_consent_postgres_repository import (
        ContactConsentPostgresRepository,
    )

    def _boom(self, cur, event):
        raise RuntimeError("audit write failed (forced by the rollback proof)")

    monkeypatch.setattr(ContactConsentPostgresRepository, "_audit_insert", _boom)
    try:
        fail = client.put(
            "/api/contacts/" + cid,
            json={"email_consent_status": "opted_in"},
            headers=admin_headers,
        )
        assert fail.status_code >= 500, fail.text
    except RuntimeError:
        pass  # TestClient re-raises server exceptions by default
    monkeypatch.undo()
    still = client.get("/api/contacts/" + cid, headers=admin_headers).json()
    assert still["email_consent_status"] == "opted_out"  # mutation rolled back
