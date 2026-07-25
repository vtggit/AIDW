"""Proving test for Issue #296 — free-form process validation endpoint."""

import re

from app.api.process_validate import router as _validate_router
from app.db.connection import get_cursor

_DEF_ID = "vtest-def-1"


def _seed_process():
    """Seed a process definition with start, service, gateway, and end steps."""
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO process_definitions (id, name, process_key, version) "
            "VALUES (%s, %s, %s, %s)",
            (_DEF_ID, "Validate Test", "proc_validate_test", "1"),
        )

        steps = [
            ("vs-start", "Start", "start_1", 0, "start", None),
            ("vs-svc", "Do Work", "svc_1", 1, "service", "${approve}"),
            ("vs-gw", "Choose", "gw_1", 2, "gateway", None),
            ("vs-end-a", "Approved", "end_a", 3, "end", None),
            ("vs-end-b", "Rejected", "end_b", 4, "end", None),
        ]
        for sid, name, key, ordinal, stype, impl in steps:
            cur.execute(
                "INSERT INTO process_steps "
                "(id, name, step_key, ordinal, step_type, service_impl, process_definition_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (sid, name, key, ordinal, stype, impl, _DEF_ID),
            )

        flows = [
            ("vf-1", "f1", "f1", "start_1", "svc_1", None, False),
            ("vf-2", "f2", "f2", "svc_1", "gw_1", None, False),
            ("vf-3", "f3", "f3", "gw_1", "end_a", None, True),
            ("vf-4", "f4", "f4", "gw_1", "end_b", "${rejected}", False),
        ]
        for fid, name, key, src, tgt, cond, default in flows:
            cur.execute(
                "INSERT INTO sequence_flows "
                "(id, name, flow_key, source_step, target_step, condition_expression, is_default, process_definition_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (fid, name, key, src, tgt, cond, default, _DEF_ID),
            )


def _row_counts():
    """Return current row counts for process_steps and sequence_flows."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS step_count FROM process_steps WHERE process_definition_id = %s",
            (_DEF_ID,),
        )
        step_count = cur.fetchone()["step_count"]

        cur.execute(
            "SELECT COUNT(*) AS flow_count FROM sequence_flows WHERE process_definition_id = %s",
            (_DEF_ID,),
        )
        flow_count = cur.fetchone()["flow_count"]
    return step_count, flow_count


def test_issue296_freeform(app, client, admin_headers):
    # Register the new router on the test app (main.py is deliberately NOT part of this change)
    app.include_router(_validate_router)

    _seed_process()

    initial_steps, initial_flows = _row_counts()

    # ---- 1. Valid delta: add a user step -----------------------------------
    valid_body = {
        "add_steps": [
            {
                "step_key": "user_1",
                "name": "User Task",
                "ordinal": 5,
                "step_type": "user",
                "form_key": "my_form",
            }
        ],
    }

    resp = client.post(
        f"/api/process-definitions/{_DEF_ID}/validate",
        headers=admin_headers,
        json=valid_body,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert "bpmn_xml" in body
    assert "svg" in body
    # The added user step should produce a bpmn:userTask element
    assert (
        "bpmn:userTask" in body["bpmn_xml"]
    ), f"Expected bpmn:userTask in generated XML, got: {body['bpmn_xml'][:500]}"
    # SVG must start with <svg (strip potential XML declaration for robust assertion)
    svg_clean = re.sub(r"^<\?xml[^>]*>\s*", "", body["svg"].lstrip())
    assert svg_clean.startswith(
        "<svg"
    ), f"SVG should start with '<svg', got: {body['svg'][:100]}"

    # ---- 2. Invalid delta: flow references non-existent step_key -----------
    invalid_body = {
        "add_flows": [
            {
                "flow_key": "bad_flow",
                "source_step": "start_1",
                "target_step": "nonexistent_step",
            }
        ],
    }

    resp = client.post(
        f"/api/process-definitions/{_DEF_ID}/validate",
        headers=admin_headers,
        json=invalid_body,
    )
    assert resp.status_code == 422, resp.text
    err_body = resp.json()
    assert "errors" in err_body and len(err_body["errors"]) > 0

    # ---- 3. Verify persistence was NOT altered -----------------------------
    final_steps, final_flows = _row_counts()
    assert initial_steps == final_steps, "process_steps count changed after validate"
    assert initial_flows == final_flows, "sequence_flows count changed after validate"
