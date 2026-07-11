"""API endpoint tests."""


def test_issue118_freeform(client):
    resp = client.get("/api/endpoint")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
