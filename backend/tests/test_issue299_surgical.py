import pytest


def test_issue299_surgical(client):
    """Verify process_validate router is registered and enforces auth."""
    response = client.post("/api/process-definitions/1/validate")
    assert response.status_code == 401, (
        f"Expected 401 Unauthorized (route exists, auth enforced), "
        f"got {response.status_code}. Route may not be registered."
    )
