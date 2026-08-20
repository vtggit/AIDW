"""Proving test for issue #487: pagination validation and X-Total-Count."""


def test_issue487_surgical(client, admin_headers, clean_database):
    # Create 3 load sequences so we have known data.
    for i in range(3):
        resp = client.post(
            "/api/load-sequences",
            json={"name": f"seq-{i}"},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text

    # --- 422 validation cases ---
    resp = client.get("/api/load-sequences?limit=0", headers=admin_headers)
    assert resp.status_code == 422
    assert "limit" in resp.text

    resp = client.get("/api/load-sequences?limit=101", headers=admin_headers)
    assert resp.status_code == 422
    assert "limit" in resp.text

    resp = client.get("/api/load-sequences?offset=-1", headers=admin_headers)
    assert resp.status_code == 422
    assert "offset" in resp.text

    # --- no-parameter request returns full list with X-Total-Count ---
    resp = client.get("/api/load-sequences", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    total = int(resp.headers["X-Total-Count"])
    assert len(body) == total
    assert total >= 3

    # --- limit=1 returns exactly 1 item with correct X-Total-Count ---
    resp = client.get("/api/load-sequences?limit=1", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert resp.headers["X-Total-Count"] == str(total)
