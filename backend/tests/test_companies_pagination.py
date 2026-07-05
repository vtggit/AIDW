"""Pagination test — GET /api/companies pages by default (20/100 enforced, #179)."""


def test_companies_list_pagination(client, admin_headers):
    ids = []
    for i in range(3):
        r = client.post(
            "/api/companies", json={"name": "page-row-" + str(i)}, headers=admin_headers
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    full = client.get("/api/companies", headers=admin_headers)
    assert full.status_code == 200, full.text
    total = int(full.headers["X-Total-Count"])
    assert total >= 3
    assert len(full.json()) == min(total, 20)  # default page size is ENFORCED
    two = client.get("/api/companies?limit=2", headers=admin_headers)
    assert two.status_code == 200 and len(two.json()) == 2
    walked = []
    for off in range(0, total, 100):
        page = client.get(
            "/api/companies?limit=100&offset=" + str(off), headers=admin_headers
        )
        walked.extend(x["id"] for x in page.json())
    assert all(i in walked for i in ids)  # offset paging reaches every row
