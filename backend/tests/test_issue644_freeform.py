"""Proof for issue #644 — a returned non-succeeded run body fails the step.

Proves that ``execute_sequence_run`` treats a step whose ``start_run`` returns a
run body whose ``status`` is anything other than ``"succeeded"`` exactly like a
step whose ``start_run`` raised: the step is marked ``failed`` with
``started_at``/``finished_at``, the remaining steps are marked ``skipped``, and
the run is marked ``failed`` — the same bookkeeping as the raised baseline. A
returned ``"succeeded"`` body keeps today's success path (every step ``success``,
run ``completed``). Each scenario monkeypatches ``app.ingest.service.start_run``.
"""

import uuid

from app.ingest import service as ingest_service


def _create_fixture(client, admin_headers, label: str) -> tuple[str, str]:
    """Create a pipeline, a load sequence, two ordered steps, and a pending run.

    Returns (pipeline_id, run_id).
    """
    pipeline_resp = client.post(
        "/api/pipelines",
        json={"name": f"p-{label}"},
        headers=admin_headers,
    )
    assert (
        pipeline_resp.status_code == 201
    ), f"Failed to create pipeline: {pipeline_resp.status_code} {pipeline_resp.text}"
    pipeline_id = pipeline_resp.json()["id"]

    seq_resp = client.post(
        "/api/load-sequences",
        json={"name": f"seq-{label}"},
        headers=admin_headers,
    )
    assert (
        seq_resp.status_code == 201
    ), f"Failed to create sequence: {seq_resp.status_code} {seq_resp.text}"
    sequence_id = seq_resp.json()["id"]

    for order_index, step_name in enumerate(("s1", "s2")):
        step_resp = client.post(
            "/api/sequence-steps",
            json={
                "name": step_name,
                "sequence_id": sequence_id,
                "pipeline_id": pipeline_id,
                "order_index": order_index,
                "label": f"step {order_index + 1}",
            },
            headers=admin_headers,
        )
        assert (
            step_resp.status_code == 201
        ), f"Failed to create step {step_name}: {step_resp.status_code} {step_resp.text}"

    run_resp = client.post(
        "/api/sequence-runs",
        json={"name": f"r-{label}", "sequence_id": sequence_id},
        headers=admin_headers,
    )
    assert (
        run_resp.status_code == 201
    ), f"Failed to create run: {run_resp.status_code} {run_resp.text}"
    return pipeline_id, run_resp.json()["id"]


def _execute(client, admin_headers, run_id: str) -> dict:
    resp = client.post(f"/api/sequence-runs/{run_id}/execute", headers=admin_headers)
    assert resp.status_code == 200, f"Execute returned {resp.status_code}: {resp.text}"
    return resp.json()


def _failure_shape(result: dict) -> dict:
    """The failure bookkeeping a raised start_run leaves behind, as comparable data.

    Run terminal state plus, per step in order: status and whether
    started_at/finished_at were set.
    """
    return {
        "run_status": result["status"],
        "run_started": result["started_at"] is not None,
        "run_finished": result["finished_at"] is not None,
        "steps": [
            {
                "status": step["status"],
                "started": step["started_at"] is not None,
                "finished": step["finished_at"] is not None,
            }
            for step in result["steps"]
        ],
    }


def test_issue644_freeform(client, admin_headers, monkeypatch):
    # --- Baseline: a step whose start_run raises — today's failure handling ---
    monkeypatch.setattr(
        ingest_service,
        "start_run",
        lambda pipeline_id: (_ for _ in ()).throw(RuntimeError("ingest boom")),
    )
    _, raised_run_id = _create_fixture(client, admin_headers, "raise")
    baseline = _failure_shape(_execute(client, admin_headers, raised_run_id))
    assert baseline["run_status"] == "failed"
    assert baseline["run_started"] is True
    assert baseline["run_finished"] is True
    assert [step["status"] for step in baseline["steps"]] == ["failed", "skipped"]
    assert baseline["steps"][0] == {
        "status": "failed",
        "started": True,
        "finished": True,
    }
    assert baseline["steps"][1] == {
        "status": "skipped",
        "started": False,
        "finished": False,
    }

    # --- Returned "failed" body: handled exactly like the raised baseline ---
    monkeypatch.setattr(
        ingest_service,
        "start_run",
        lambda pipeline_id: {
            "id": str(uuid.uuid4()),
            "pipeline_id": pipeline_id,
            "status": "failed",
            "error_detail": "boom",
        },
    )
    _, failed_run_id = _create_fixture(client, admin_headers, "failed")
    assert _failure_shape(_execute(client, admin_headers, failed_run_id)) == baseline

    # --- Returned "deleted" stub: same failure handling ---
    monkeypatch.setattr(
        ingest_service,
        "start_run",
        lambda pipeline_id: {"id": "deleted-run", "status": "deleted"},
    )
    _, deleted_run_id = _create_fixture(client, admin_headers, "deleted")
    assert _failure_shape(_execute(client, admin_headers, deleted_run_id)) == baseline

    # --- Returned "succeeded" body: today's success path is kept ---
    monkeypatch.setattr(
        ingest_service,
        "start_run",
        lambda pipeline_id: {
            "id": str(uuid.uuid4()),
            "pipeline_id": pipeline_id,
            "status": "succeeded",
            "inserts": 2,
            "updates": 0,
            "skipped_no_key": 0,
        },
    )
    _, succeeded_run_id = _create_fixture(client, admin_headers, "succeeded")
    result = _execute(client, admin_headers, succeeded_run_id)
    assert result["status"] == "completed"
    assert result["started_at"] is not None
    assert result["finished_at"] is not None
    assert [step["status"] for step in result["steps"]] == ["success", "success"]
    for step in result["steps"]:
        assert step["started_at"] is not None
        assert step["finished_at"] is not None
