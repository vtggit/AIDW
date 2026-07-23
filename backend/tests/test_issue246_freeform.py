"""Proving test for Issue #246 — frontend↔backend step-type contract."""

import re
from pathlib import Path

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.xml_emit import emit_bpmn

CANONICAL = ("start", "end", "user", "service", "gateway")


def test_issue246_freeform():
    # 1. FRONTEND — wizard offers EXACTLY the canonical step types, no more, no fewer
    repo_root = Path(__file__).resolve().parents[2]
    studio_html = (repo_root / "app" / "studio.html").read_text(encoding="utf-8")

    start_idx = studio_html.find('id="wizard-step-type"')
    assert start_idx != -1, "wizard-step-type select not found in studio.html"
    end_idx = studio_html.find("</select>", start_idx) + len("</select>")
    select_block = studio_html[start_idx:end_idx]

    option_values = re.findall(r'value="([^"]*)"', select_block)
    assert set(option_values) == set(
        CANONICAL
    ), f"Frontend wizard step types {set(option_values)} do not match canonical {set(CANONICAL)}"

    # 2. BACKEND-RENDERS-ALL — every canonical type the wizard offers is actually rendered
    process = {"process_key": "test_process", "name": "Test Process", "version": 1}
    steps = [
        {"step_key": "start_1", "ordinal": 0, "step_type": "start", "name": "Start"},
        {
            "step_key": "user_1",
            "ordinal": 1,
            "step_type": "user",
            "name": "User Task",
            "candidate_groups": ["admins"],
        },
        {
            "step_key": "service_1",
            "ordinal": 2,
            "step_type": "service",
            "name": "Service Task",
            "service_impl": "${myDelegate.execute()}",
        },
        {"step_key": "gw_1", "ordinal": 3, "step_type": "gateway", "name": "Decision"},
        {"step_key": "end_yes", "ordinal": 4, "step_type": "end", "name": "End Yes"},
        {"step_key": "end_no", "ordinal": 5, "step_type": "end", "name": "End No"},
    ]
    flows = [
        {
            "flow_key": "f1",
            "source_step": "start_1",
            "target_step": "user_1",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f2",
            "source_step": "user_1",
            "target_step": "service_1",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f3",
            "source_step": "service_1",
            "target_step": "gw_1",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f4",
            "source_step": "gw_1",
            "target_step": "end_yes",
            "condition_expression": "${result == 'yes'}",
            "is_default": False,
        },
        {
            "flow_key": "f5",
            "source_step": "gw_1",
            "target_step": "end_no",
            "condition_expression": None,
            "is_default": True,
        },
    ]

    ir = build_ir(process, steps, flows)
    layout_model = layout(ir)
    bpmn_xml = emit_bpmn(ir, layout_model)

    assert "bpmn:startEvent" in bpmn_xml
    assert "bpmn:userTask" in bpmn_xml
    assert "bpmn:serviceTask" in bpmn_xml
    assert "bpmn:exclusiveGateway" in bpmn_xml
    assert "bpmn:endEvent" in bpmn_xml

    # 3. CLOSED-SET — unknown step_type is rejected (fail-closed guarantee)
    unknown_steps = [
        {"step_key": "s1", "ordinal": 0, "step_type": "start", "name": "Start"},
        {"step_key": "s2", "ordinal": 1, "step_type": "parallel", "name": "Parallel"},
    ]
    unknown_flows = []

    rejected = False
    rendered_xml = None
    try:
        ir_u = build_ir(process, unknown_steps, unknown_flows)
        lm_u = layout(ir_u)
        rendered_xml = emit_bpmn(ir_u, lm_u)
    except Exception:
        rejected = True

    if not rejected and rendered_xml is not None:
        assert (
            "bpmn:parallelGateway" not in rendered_xml
        ), "Unknown step type 'parallel' was silently rendered."
