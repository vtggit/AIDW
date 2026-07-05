"""Pagination hardening — defaults, caps, validation, and totals on every list."""


def test_list_pagination_hardening(client, admin_headers):
    endpoints = [
        "/api/activities",
        "/api/companies",
        "/api/contacts",
        "/api/deal-outcomes",
        "/api/leads",
        "/api/tags",
        "/api/templates",
    ]
    # table missing from migrations -> the 200-path 503s (pre-existing, filed);
    # FastAPI validation fires before the DB, so the 422 contract still holds
    validation_only = ["/api/sales-goals"]
    for ep in endpoints + validation_only:
        assert (
            client.get(ep + "?limit=-1", headers=admin_headers).status_code == 422
        ), ep
        assert (
            client.get(ep + "?limit=101", headers=admin_headers).status_code == 422
        ), ep
        assert (
            client.get(ep + "?offset=-1", headers=admin_headers).status_code == 422
        ), ep
    for ep in endpoints:
        ok = client.get(ep, headers=admin_headers)
        assert ok.status_code == 200, ep + ": " + ok.text
        assert ok.headers.get("X-Total-Count") is not None, ep
        assert len(ok.json()) <= 20, ep
    for i in range(25):
        r = client.post(
            "/api/companies", json={"name": f"Page Co {i:02d}"}, headers=admin_headers
        )
        assert r.status_code == 201, r.text
    full = client.get("/api/companies", headers=admin_headers)
    total = int(full.headers["X-Total-Count"])
    assert len(full.json()) == 20 and total >= 25  # default page, true total
    rest = client.get("/api/companies?limit=100&offset=20", headers=admin_headers)
    assert len(rest.json()) == total - 20  # offset walks the whole set
    five = client.get("/api/companies?limit=5", headers=admin_headers)
    assert len(five.json()) == 5
