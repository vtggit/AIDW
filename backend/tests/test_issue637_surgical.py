"""Proving test for issue #637: service identifier is 'aidw-backend'."""


def test_issue637_surgical(client):
    """Both /api/health and /api/health/ready report service='aidw-backend'."""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "aidw-backend"

    r2 = client.get("/api/health/ready")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["service"] == "aidw-backend"
