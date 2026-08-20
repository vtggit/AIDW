"""Pagination test — GET /api/sequence-runs?limit=&offset= pages the list; omitting both is unchanged."""


def test_sequence_runs_list_pagination(client, admin_headers):
    ids = []
    for i in range(3):
        r = client.post(
            "/api/sequence-runs",
            json={"name": "page-row-" + str(i)},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    full = client.get("/api/sequence-runs", headers=admin_headers)
    assert full.status_code == 200, full.text
    total = len(full.json())
    assert total >= 3
    assert all(
        i in [x["id"] for x in full.json()] for i in ids
    )  # no-params returns all
    two = client.get("/api/sequence-runs?limit=2", headers=admin_headers)
    assert two.status_code == 200 and len(two.json()) == 2
    allp = client.get("/api/sequence-runs?limit=" + str(total), headers=admin_headers)
    assert len(allp.json()) == total
    off = client.get(
        "/api/sequence-runs?limit=" + str(total) + "&offset=1", headers=admin_headers
    )
    assert len(off.json()) == total - 1
