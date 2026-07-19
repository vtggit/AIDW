"""Proving tests — workflows sidecar proxy (engine-generated: sidecar-proxy lane).

The sidecar client functions are monkeypatched: CI never talks to a live
engine.  Pins the allowlist 422s (unknown variable name / missing required),
the start 202, status 200/404 mapping, and the config fail-closed 503.
"""

import app.workflows.flowable_client as _sidecar


def test_workflows_proxy(client, admin_headers, monkeypatch):
    async def fake_start(process_key, variables):
        assert process_key == "aidwRtbf"
        assert sorted(variables) == sorted(["dsr_request_id"])
        return "inst-0001"

    monkeypatch.setattr(_sidecar, "start_process", fake_start)
    resp = client.post(
        "/api/workflows/rtbf/start",
        json={"dsr_request_id": "ref-0"},
        headers=admin_headers,
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["instance_id"] == "inst-0001"


def test_workflows_start_requires_auth(client):
    resp = client.post("/api/workflows/rtbf/start", json={"dsr_request_id": "ref-0"})
    assert resp.status_code in (
        401,
        403,
    ), "workflow-start must require authentication (AIDW#192)"


def test_workflows_start_rejects_unknown_variable(client, admin_headers, monkeypatch):
    async def fake_start(process_key, variables):  # pragma: no cover — must not run
        raise AssertionError("allowlist must reject before the sidecar is called")

    monkeypatch.setattr(_sidecar, "start_process", fake_start)
    resp = client.post(
        "/api/workflows/rtbf/start",
        json={"dsr_request_id": "ref-0", "email": "x@example.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 422, (
        "an unknown variable name must be a 422 at the boundary — the "
        "server-side half of the OQ-6 opaque-reference rail"
    )


def test_workflows_start_requires_all_references(client, admin_headers):
    resp = client.post("/api/workflows/rtbf/start", json={}, headers=admin_headers)
    assert resp.status_code == 422


def test_workflows_start_maps_missing_config_to_503(client, admin_headers, monkeypatch):
    async def fake_start(process_key, variables):
        raise _sidecar.SidecarConfigError("sidecar not configured")

    monkeypatch.setattr(_sidecar, "start_process", fake_start)
    resp = client.post(
        "/api/workflows/rtbf/start",
        json={"dsr_request_id": "ref-0"},
        headers=admin_headers,
    )
    assert resp.status_code == 503


def test_workflows_status_maps_found_and_missing(client, admin_headers, monkeypatch):
    async def fake_get(instance_id):
        if instance_id == "inst-0001":
            # real Flowable historic shape: key lives in processDefinitionId
            return {
                "id": "inst-0001",
                "processDefinitionId": "aidwRtbf:1:abc",
                "endTime": None,
            }
        return None

    monkeypatch.setattr(_sidecar, "get_instance", fake_get)
    ok = client.get("/api/workflows/instances/inst-0001", headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["ended"] is False
    assert ok.json()["process_key"] == "aidwRtbf"  # derived from the id fallback
    missing = client.get("/api/workflows/instances/inst-gone", headers=admin_headers)
    assert missing.status_code == 404
