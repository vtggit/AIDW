"""Filter test — GET /api/leads?company_id= narrows the list; omitting it is unchanged."""


def test_leads_list_filters_by_company_id(client, admin_headers):
    parent = client.post(
        "/api/companies",
        json={"name": "Filter Parent (leads_company_id_filter)"},
        headers=admin_headers,
    )
    assert parent.status_code == 201, parent.text
    val = parent.json()["id"]
    linked = client.post(
        "/api/leads", json={"name": "linked", "company_id": val}, headers=admin_headers
    )
    assert linked.status_code == 201, linked.text
    unlinked = client.post(
        "/api/leads", json={"name": "unlinked"}, headers=admin_headers
    )
    assert unlinked.status_code == 201, unlinked.text
    filtered = client.get("/api/leads?company_id=" + val, headers=admin_headers)
    assert filtered.status_code == 200, filtered.text
    ids = [x["id"] for x in filtered.json()]
    assert linked.json()["id"] in ids
    assert unlinked.json()["id"] not in ids
    everything = client.get("/api/leads", headers=admin_headers)
    all_ids = [x["id"] for x in everything.json()]
    assert linked.json()["id"] in all_ids and unlinked.json()["id"] in all_ids
