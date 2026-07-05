"""Visibility test — GET /api/companies?include_deleted=true returns soft-deleted rows."""


def test_companies_include_deleted(client, admin_headers):
    alive = client.post(
        "/api/companies", json={"name": "Visible Co"}, headers=admin_headers
    )
    assert alive.status_code == 201, alive.text
    doomed = client.post(
        "/api/companies", json={"name": "Hidden Co"}, headers=admin_headers
    )
    assert doomed.status_code == 201, doomed.text
    did = doomed.json()["id"]
    assert (
        client.delete("/api/companies/" + did, headers=admin_headers).status_code == 204
    )
    default_ids = [
        x["id"] for x in client.get("/api/companies", headers=admin_headers).json()
    ]
    assert did not in default_ids  # default stays exclusive
    both = client.get("/api/companies?include_deleted=true", headers=admin_headers)
    assert both.status_code == 200, both.text
    both_ids = [x["id"] for x in both.json()]
    assert did in both_ids  # the soft-deleted row is returned
    assert alive.json()["id"] in both_ids  # alongside active rows
