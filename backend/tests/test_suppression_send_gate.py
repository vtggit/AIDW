"""Suppression list + unsubscribe + the send gate (#186), on the #185 consent model."""


def test_suppression_send_gate(client, admin_headers):
    a = client.post(
        "/api/suppressions",
        json={"email": "Blocked@Example.com", "reason": "manual", "note": "test"},
        headers=admin_headers,
    )
    assert a.status_code == 201, a.text
    sid = a.json()["id"]
    dup = client.post(
        "/api/suppressions",
        json={"email": "blocked@example.com", "reason": "manual"},
        headers=admin_headers,
    )
    assert dup.status_code == 409, dup.text  # case-variant duplicate -> clear 409
    bad = client.post(
        "/api/suppressions",
        json={"email": "x@y.z", "reason": "banana"},
        headers=admin_headers,
    )
    assert bad.status_code == 422 and "reason" in bad.text
    lst = client.get("/api/suppressions", headers=admin_headers)
    assert lst.status_code == 200 and lst.headers.get("X-Total-Count") is not None
    assert len(lst.json()) <= 20  # the #179 hardened contract
    assert (
        client.get("/api/suppressions?limit=-1", headers=admin_headers).status_code
        == 422
    )
    # the send gate: suppressed address -> not sendable
    g1 = client.get(
        "/api/suppressions/may-send?email=BLOCKED@example.com", headers=admin_headers
    ).json()
    assert g1["may_send"] is False and any("suppressed" in r for r in g1["reasons"])
    # an opted-in contact with a clean address -> sendable
    c = client.post(
        "/api/contacts",
        json={"name": "Gate Target", "email": "gate.target@example.com"},
        headers=admin_headers,
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    up = client.put(
        "/api/contacts/" + cid,
        json={"email_consent_status": "opted_in", "consent_source": "form"},
        headers=admin_headers,
    )
    assert up.status_code == 200, up.text
    g2 = client.get(
        "/api/suppressions/may-send?email=gate.target@example.com",
        headers=admin_headers,
    ).json()
    assert g2["may_send"] is True and g2["reasons"] == []
    # the transactional unsubscribe: suppression + consent flip + audit, one call
    u = client.post(
        "/api/suppressions/unsubscribe",
        json={"contact_id": cid},
        headers=admin_headers,
    )
    assert u.status_code == 200, u.text
    assert u.json()["may_send"] is False
    got = client.get("/api/contacts/" + cid, headers=admin_headers).json()
    assert got["email_consent_status"] == "opted_out"  # #185 model flipped
    assert got["consent_source"] == "unsubscribe"
    aud = client.get("/api/audit?entity_type=contact", headers=admin_headers).json()
    events = [
        e
        for e in aud
        if e["entity_id"] == cid
        and e["action"] == "consent_change"
        and e["details"].get("source") == "unsubscribe"
    ]
    assert len(events) == 1
    # removal re-enables ONLY the suppression half (consent still opted_out)
    sup = [
        s
        for s in client.get("/api/suppressions?limit=100", headers=admin_headers).json()
        if s["email"].lower() == "gate.target@example.com"
    ]
    assert len(sup) == 1
    rm = client.delete("/api/suppressions/" + sup[0]["id"], headers=admin_headers)
    assert rm.status_code == 204
    g3 = client.get(
        "/api/suppressions/may-send?email=gate.target@example.com",
        headers=admin_headers,
    ).json()
    assert g3["may_send"] is False
    assert any("opted_out" in r for r in g3["reasons"])
    rm0 = client.delete("/api/suppressions/" + sid, headers=admin_headers)
    assert rm0.status_code == 204
