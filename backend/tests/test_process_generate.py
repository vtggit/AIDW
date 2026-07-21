"""Proving test for the Path B Phase 3 /generate endpoint: Phase-1 rows -> BPMN XML + SVG.

Seeds a real process (start -> service -> exclusive gateway -> two ends) across the
process_definitions / process_steps / sequence_flows tables, calls the endpoint, and checks the
generated BPMN and SVG are well-formed via the standard library (no lxml dependency).
"""

from xml.dom.minidom import parseString

from app.db.connection import get_cursor

_DEF_ID = "pgtest-def-1"


def _seed_process():
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO process_definitions (id, name, process_key, version) "
            "VALUES (%s, %s, %s, %s)",
            (_DEF_ID, "Generate Test", "proc_generate_test", "1"),
        )
        steps = [
            # id, name, step_key, ordinal, step_type, service_impl
            ("pgs-start", "Start", "start_1", 0, "start", None),
            ("pgs-svc", "Do Work", "svc_1", 1, "service", "${approve}"),
            ("pgs-gw", "Choose", "gw_1", 2, "gateway", None),
            ("pgs-a", "Approved", "end_a", 3, "end", None),
            ("pgs-b", "Rejected", "end_b", 4, "end", None),
        ]
        for sid, name, key, ordinal, stype, impl in steps:
            cur.execute(
                "INSERT INTO process_steps "
                "(id, name, step_key, ordinal, step_type, service_impl, process_definition_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (sid, name, key, ordinal, stype, impl, _DEF_ID),
            )
        flows = [
            # id, name, flow_key, source_step, target_step, condition, is_default
            ("pgf-1", "f1", "f1", "start_1", "svc_1", None, False),
            ("pgf-2", "f2", "f2", "svc_1", "gw_1", None, False),
            ("pgf-3", "f3", "f3", "gw_1", "end_a", None, True),
            ("pgf-4", "f4", "f4", "gw_1", "end_b", "${rejected}", False),
        ]
        for fid, name, key, src, tgt, cond, default in flows:
            cur.execute(
                "INSERT INTO sequence_flows "
                "(id, name, flow_key, source_step, target_step, condition_expression, "
                "is_default, process_definition_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (fid, name, key, src, tgt, cond, default, _DEF_ID),
            )


def test_generate_process_diagram(client, admin_headers):
    _seed_process()

    resp = client.post(
        f"/api/process-definitions/{_DEF_ID}/generate", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["process_key"] == "proc_generate_test"

    # BPMN is well-formed XML rooted at <definitions> containing exactly one <process>
    bpmn = parseString(body["bpmn_xml"])
    assert bpmn.documentElement.localName == "definitions"
    assert len(bpmn.getElementsByTagName("bpmn:process")) == 1
    # one BPMNShape per step (5), one BPMNEdge per flow (4)
    assert len(bpmn.getElementsByTagName("bpmndi:BPMNShape")) == 5
    assert len(bpmn.getElementsByTagName("bpmndi:BPMNEdge")) == 4

    # SVG is well-formed XML rooted at <svg>
    svg = parseString(body["svg"])
    assert svg.documentElement.localName == "svg"


def test_generate_missing_definition_404(client, admin_headers):
    resp = client.post(
        "/api/process-definitions/does-not-exist/generate", headers=admin_headers
    )
    assert resp.status_code == 404
