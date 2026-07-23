"""Surgical fix for Issue #286: sequenceFlow conditionExpression emission."""

from xml.dom.minidom import parseString

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.xml_emit import emit_bpmn


def test_issue286_surgical():
    process = {"process_key": "proc_286", "name": "Issue 286", "version": 1}
    steps = [
        {"step_key": "start_1", "ordinal": 0, "step_type": "start", "name": "Start"},
        {"step_key": "gw_1", "ordinal": 1, "step_type": "gateway", "name": "Gateway"},
        {"step_key": "end_a", "ordinal": 2, "step_type": "end", "name": "End A"},
        {"step_key": "end_b", "ordinal": 3, "step_type": "end", "name": "End B"},
    ]
    flows = [
        # Plain unconditioned flow elsewhere
        {"flow_key": "f_uncond", "source_step": "start_1", "target_step": "gw_1"},
        # Conditioned outgoing flow from gateway
        {
            "flow_key": "f_cond",
            "source_step": "gw_1",
            "target_step": "end_a",
            "condition_expression": "${approved}",
        },
        # Default outgoing flow from gateway
        {
            "flow_key": "f_default",
            "source_step": "gw_1",
            "target_step": "end_b",
            "is_default": True,
        },
    ]

    process_ir = build_ir(process, steps, flows)
    layout_model = layout(process_ir)
    xml_str = emit_bpmn(process_ir, layout_model)

    doc = parseString(xml_str)
    proc = doc.getElementsByTagName("bpmn:process")[0]

    def get_flow(fid):
        for f in proc.getElementsByTagName("bpmn:sequenceFlow"):
            if f.getAttribute("id") == fid:
                return f
        raise ValueError(f"Flow {fid} not found in emitted XML")

    f_uncond = get_flow("f_uncond")
    f_cond = get_flow("f_cond")
    f_default = get_flow("f_default")

    # (a) conditioned flow carries a conditionExpression with the exact condition text
    cond_exprs = f_cond.getElementsByTagName("bpmn:conditionExpression")
    assert (
        len(cond_exprs) == 1
    ), "Conditioned flow must have exactly one conditionExpression"
    assert cond_exprs[0].firstChild.nodeValue == "${approved}"

    # (b) default flow and unconditioned flow have no conditionExpression child
    assert len(f_default.getElementsByTagName("bpmn:conditionExpression")) == 0
    assert len(f_uncond.getElementsByTagName("bpmn:conditionExpression")) == 0

    # (c) no empty conditionExpression element exists anywhere in the document
    all_cond_exprs = doc.getElementsByTagName("bpmn:conditionExpression")
    for ce in all_cond_exprs:
        text = ce.firstChild.nodeValue if ce.firstChild else ""
        assert (
            text.strip() != ""
        ), f"Found empty conditionExpression in flow {ce.parentNode.getAttribute('id')}"
