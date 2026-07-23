"""Proving test for Issue #232 — BPMN 2.0 XML emitter."""

import random
import xml.dom.minidom as minidom

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.xml_emit import emit_bpmn


def test_issue232_freeform():
    """Assert the BPMN 2.0 XML emitter produces well-formed, deterministic output."""
    process = {
        "process_key": "test_process",
        "name": "Test Process",
        "version": 1,
    }

    steps_data = [
        {"step_key": "start_1", "ordinal": 0, "step_type": "start", "name": "Start"},
        {
            "step_key": "service_1",
            "ordinal": 1,
            "step_type": "service",
            "name": "Service Task",
            "service_impl": "${myService}",
        },
        {
            "step_key": "gateway_1",
            "ordinal": 2,
            "step_type": "gateway",
            "name": "Decision",
        },
        {"step_key": "end_yes", "ordinal": 3, "step_type": "end", "name": "End Yes"},
        {"step_key": "end_no", "ordinal": 4, "step_type": "end", "name": "End No"},
    ]

    flows_data = [
        {
            "flow_key": "f1",
            "source_step": "start_1",
            "target_step": "service_1",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f2",
            "source_step": "service_1",
            "target_step": "gateway_1",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f3",
            "source_step": "gateway_1",
            "target_step": "end_yes",
            "condition_expression": "${result == 'yes'}",
            "is_default": False,
        },
        {
            "flow_key": "f4",
            "source_step": "gateway_1",
            "target_step": "end_no",
            "condition_expression": None,
            "is_default": True,
        },
    ]

    process_ir = build_ir(process, steps_data, flows_data)
    layout_model = layout(process_ir)

    xml_str = emit_bpmn(process_ir, layout_model)

    doc = minidom.parseString(xml_str)

    assert doc.documentElement.localName == "definitions"

    processes = [
        c
        for c in doc.documentElement.childNodes
        if hasattr(c, "localName") and c.localName == "process"
    ]
    assert len(processes) == 1
    assert processes[0].getAttribute("id") == process_ir.process_key

    shapes = doc.getElementsByTagName("bpmndi:BPMNShape")
    assert len(shapes) == len(process_ir.steps)

    edges = doc.getElementsByTagName("bpmndi:BPMNEdge")
    assert len(edges) == len(process_ir.flows)

    xml_str2 = emit_bpmn(process_ir, layout_model)
    assert xml_str == xml_str2

    rng = random.Random(42)
    shuffled_steps = list(steps_data)
    rng.shuffle(shuffled_steps)
    shuffled_flows = list(flows_data)
    rng.shuffle(shuffled_flows)

    process_ir_shuffled = build_ir(process, shuffled_steps, shuffled_flows)
    layout_model_shuffled = layout(process_ir_shuffled)
    xml_str3 = emit_bpmn(process_ir_shuffled, layout_model_shuffled)
    assert xml_str == xml_str3
