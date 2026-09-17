"""Proving test for Issue #565 — atomic pending-to-running claim."""

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.db.connection import get_cursor
from app.services.sequence_execution_service import execute_sequence_run


def test_issue565_surgical(client, admin_headers):
    """Concurrent claim: if the run is already 'running' in the DB but the
    in-memory read (get_by_id) still sees NULL/pending, the atomic conditional
    UPDATE must detect the conflict and raise 409 — not proceed to create
    duplicate run_steps and 500 on the unique constraint."""

    # --- Setup: create prerequisite entities ---
    pipeline_resp = client.post(
        "/api/pipelines", json={"name": "p1"}, headers=admin_headers
    )
    assert pipeline_resp.status_code == 201
    pipeline_id = pipeline_resp.json()["id"]

    seq_resp = client.post(
        "/api/load-sequences", json={"name": "seq1"}, headers=admin_headers
    )
    assert seq_resp.status_code == 201
    sequence_id = seq_resp.json()["id"]

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
    assert step_resp.status_code == 201
    step_id = step_resp.json()["id"]

    run_resp = client.post(
        "/api/sequence-runs",
        json={"name": "r1", "sequence_id": sequence_id},
        headers=admin_headers,
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # --- Simulate a concurrent worker that already claimed the run ---
    with get_cursor() as cur:
        cur.execute(
            "UPDATE sequence_runs SET status = 'running', "
            "started_at = now()::text WHERE id = %s",
            (run_id,),
        )
        cur.execute(
            "INSERT INTO sequence_run_steps "
            "(id, name, run_id, step_id, status, started_at, finished_at) "
            "VALUES (%s, 's1', %s, %s, 'running', now()::text, NULL)",
            (str(uuid.uuid4()), run_id, step_id),
        )

    # --- Call execute_sequence_run with a stale read ---
    # Patch get_by_id to return status=None, simulating the TOCTOU window
    # where the read saw NULL before the other worker updated the row.
    stale_run = {"id": run_id, "sequence_id": sequence_id, "status": None}

    with (
        patch(
            "app.services.sequence_execution_service._run_repo.get_by_id",
            return_value=stale_run,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        execute_sequence_run(run_id)

    # The atomic conditional UPDATE must detect the conflict → 409.
    # The old (non-atomic) code would pass the in-memory check, do an
    # unconditional update, then hit the unique constraint on
    # sequence_run_steps (run_id, step_id) → unhandled IntegrityError.
    assert exc_info.value.status_code == 409, (
        f"Expected 409 conflict, got {exc_info.value.status_code}: "
        f"{exc_info.value.detail}"
    )
