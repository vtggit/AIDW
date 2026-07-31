"""Proving test for Issue #382 — sequence run execution."""


def test_issue382_freeform(client, admin_headers):
    """Execute a pending sequence run processes steps in order and records per-step state.

    Deterministic gate-environment path: fixture pipelines have no ingestible source, so
    execute yields step 1 failure, later steps skipped, run failed, HTTP 200 — do NOT assert
    step success (unreachable in the gate); plus the 409 on re-execute.
    """

    # --- Fixture chain: create prerequisite entities ---

    # 1) POST /api/pipelines with {"name": "p1"}
    pipeline_resp = client.post(
        "/api/pipelines",
        json={"name": "p1"},
        headers=admin_headers,
    )
    assert (
        pipeline_resp.status_code == 201
    ), f"Failed to create pipeline: {pipeline_resp.status_code} {pipeline_resp.text}"
    pipeline = pipeline_resp.json()
    pipeline_id = pipeline["id"]

    # 2) POST /api/load-sequences with {"name": "seq1"}
    seq_resp = client.post(
        "/api/load-sequences",
        json={"name": "seq1"},
        headers=admin_headers,
    )
    assert (
        seq_resp.status_code == 201
    ), f"Failed to create sequence: {seq_resp.status_code} {seq_resp.text}"
    sequence = seq_resp.json()
    sequence_id = sequence["id"]

    # 3) POST /api/sequence-steps with step data
    step_resp = client.post(
        "/api/sequence-steps",
        json={
            "name": "s1",
            "sequence_id": sequence_id,
            "pipeline_id": pipeline_id,
            "order_index": 0,
            "label": "step 1",
        },
        headers=admin_headers,
    )
    assert (
        step_resp.status_code == 201
    ), f"Failed to create step: {step_resp.status_code} {step_resp.text}"

    # Create a second step so we can verify skipping behavior
    step2_resp = client.post(
        "/api/sequence-steps",
        json={
            "name": "s2",
            "sequence_id": sequence_id,
            "pipeline_id": pipeline_id,
            "order_index": 1,
            "label": "step 2",
        },
        headers=admin_headers,
    )
    assert (
        step2_resp.status_code == 201
    ), f"Failed to create step 2: {step2_resp.status_code} {step2_resp.text}"

    # 4) POST /api/sequence-runs with {"name": "r1", "sequence_id": ...}
    run_resp = client.post(
        "/api/sequence-runs",
        json={"name": "r1", "sequence_id": sequence_id},
        headers=admin_headers,
    )
    assert (
        run_resp.status_code == 201
    ), f"Failed to create run: {run_resp.status_code} {run_resp.text}"
    run = run_resp.json()
    run_id = run["id"]

    # --- Execute the run ---

    execute_resp = client.post(
        f"/api/sequence-runs/{run_id}/execute",
        headers=admin_headers,
    )
    assert (
        execute_resp.status_code == 200
    ), f"Execute returned {execute_resp.status_code}: {execute_resp.text}"

    result = execute_resp.json()

    # The run should be marked as failed because the pipeline has no ingestible source
    assert (
        result["status"] == "failed"
    ), f"Expected status 'failed', got '{result['status']}'"
    assert result["started_at"] is not None, "Run should have started_at set"
    assert result["finished_at"] is not None, "Failed run should have finished_at set"

    # Verify steps are included in the response
    assert "steps" in result, "Response should include 'steps' key"
    steps = result["steps"]
    assert len(steps) == 2, f"Expected 2 steps, got {len(steps)}"

    # First step should be failed (pipeline has no source to ingest from)
    first_step = steps[0]
    assert (
        first_step["status"] == "failed"
    ), f"First step expected 'failed', got '{first_step['status']}'"
    assert first_step["started_at"] is not None, "Failed step should have started_at"
    assert first_step["finished_at"] is not None, "Failed step should have finished_at"

    # Second step should be skipped (because first step failed)
    second_step = steps[1]
    assert (
        second_step["status"] == "skipped"
    ), f"Second step expected 'skipped', got '{second_step['status']}'"

    # --- Re-execute should return 409 ---

    re_execute_resp = client.post(
        f"/api/sequence-runs/{run_id}/execute",
        headers=admin_headers,
    )
    assert (
        re_execute_resp.status_code == 409
    ), f"Re-execute expected 409, got {re_execute_resp.status_code}: {re_execute_resp.text}"
