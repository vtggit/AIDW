"""Soft-delete test — DELETE /api/companies marks deleted_at; reads exclude; links survive."""


def test_companies_soft_delete(client, admin_headers):
    made = client.post(
        "/api/companies", json={"name": "Soft Target"}, headers=admin_headers
    )
    assert made.status_code == 201, made.text
    rid = made.json()["id"]
    child = client.post(
        "/api/contacts", json={"name": "kept", "company_id": rid}, headers=admin_headers
    )
    assert child.status_code == 201, child.text
    gone = client.delete("/api/companies/" + rid, headers=admin_headers)
    assert gone.status_code == 204, gone.text
    assert client.get("/api/companies/" + rid, headers=admin_headers).status_code == 404
    ids = [x["id"] for x in client.get("/api/companies", headers=admin_headers).json()]
    assert rid not in ids  # excluded from the default list
    again = client.delete("/api/companies/" + rid, headers=admin_headers)
    assert again.status_code == 404  # second delete 404s, exactly like today
    rows = client.get("/api/contacts", headers=admin_headers).json()
    row = next(x for x in rows if x["id"] == child.json()["id"])
    assert row["company_id"] == rid  # the link SURVIVES (no cascade unlink)
