"""Proving test for Issue #238 — SVG emission from BPMN IR + layout."""

import random
import xml.dom.minidom

from app.bpmn.ir import ProcessIR, build_ir
from app.bpmn.layout import LayoutModel, layout
from app.bpmn.svg_emit import emit_svg


def test_issue238_freeform() -> None:
    """Construct a reference process via ``build_ir``, compute layout,
    emit SVG, and assert structural + determinism properties."""

    # --- build IR with REAL StepIR / FlowIR objects -------------------
    process = {"process_key": "proc-1", "name": "Test Process", "version": 1}

    steps = [
        {
            "step_key": "start",
            "ordinal": 0,
            "step_type": "start",
            "name": "Start",
        },
        {
            "step_key": "task-1",
            "ordinal": 1,
            "step_type": "service",
            "name": "Service Task",
            "service_impl": "${my_service.execute()}",
        },
        {
            "step_key": "gw-1",
            "ordinal": 2,
            "step_type": "gateway",
            "name": "Exclusive Gateway",
        },
        {
            "step_key": "end-a",
            "ordinal": 3,
            "step_type": "end",
            "name": "End A",
        },
        {
            "step_key": "end-b",
            "ordinal": 4,
            "step_type": "end",
            "name": "End B",
        },
    ]

    flows = [
        {"flow_key": "f1", "source_step": "start", "target_step": "task-1"},
        {"flow_key": "f2", "source_step": "task-1", "target_step": "gw-1"},
        {
            "flow_key": "f3",
            "source_step": "gw-1",
            "target_step": "end-a",
            "is_default": True,
        },
        {
            "flow_key": "f4",
            "source_step": "gw-1",
            "target_step": "end-b",
            "condition_expression": "${score > 50}",
            "is_default": False,
        },
    ]

    process_ir: ProcessIR = build_ir(process, steps, flows)
    layout_model: LayoutModel = layout(process_ir)

    # --- emit SVG -----------------------------------------------------
    svg_str = emit_svg(process_ir, layout_model)

    # --- assert well-formed XML via standard-library minidom ----------
    dom = xml.dom.minidom.parseString(svg_str)

    root = dom.documentElement
    assert root.localName == "svg"

    width = int(root.getAttribute("width"))
    height = int(root.getAttribute("height"))
    viewBox = root.getAttribute("viewBox")
    assert viewBox == f"0 0 {width} {height}"

    # --- one shape element per step -----------------------------------
    shape_elements = (
        dom.getElementsByTagName("rect")
        + dom.getElementsByTagName("circle")
        + dom.getElementsByTagName("polygon")
    )
    assert len(shape_elements) == len(process_ir.steps)

    # --- one polyline per sequence ------------------------------------
    polylines = dom.getElementsByTagName("polyline")
    assert len(polylines) == len(process_ir.flows)

    # --- determinism: identical on repeated calls ---------------------
    svg_str_2 = emit_svg(process_ir, layout_model)
    assert svg_str == svg_str_2

    # --- determinism: input order independence ------------------------
    shuffled_steps = list(steps)
    random.shuffle(shuffled_steps)
    shuffled_flows = list(flows)
    random.shuffle(shuffled_flows)

    process_ir_shuffled = build_ir(process, shuffled_steps, shuffled_flows)
    layout_model_shuffled = layout(process_ir_shuffled)
    svg_str_3 = emit_svg(process_ir_shuffled, layout_model_shuffled)
    assert svg_str == svg_str_3
