"""Reference-validation test — a bogus company_id returns a structured 422, not a 5xx."""


def test_company_id_bad_reference_returns_4xx(client, admin_headers):
    bad = client.post(
        "/api/contacts",
        json={"name": "x", "company_id": "no-such-ref"},
        headers=admin_headers,
    )
    assert bad.status_code == 422, "/api/contacts: " + bad.text
    assert "company_id" in bad.text or "companies" in bad.text
    bad = client.post(
        "/api/leads",
        json={"name": "x", "company_id": "no-such-ref"},
        headers=admin_headers,
    )
    assert bad.status_code == 422, "/api/leads: " + bad.text
    assert "company_id" in bad.text or "companies" in bad.text
    parent = client.post(
        "/api/companies", json={"name": "Ref Target"}, headers=admin_headers
    )
    assert parent.status_code == 201, parent.text
    ok = client.post(
        "/api/contacts",
        json={"name": "linked", "company_id": parent.json()["id"]},
        headers=admin_headers,
    )
    assert ok.status_code == 201, ok.text  # a valid reference still works
