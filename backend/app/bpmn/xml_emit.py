"""BPMN 2.0 XML document emitter."""

from __future__ import annotations

import xml.sax.saxutils as saxutils

from app.bpmn.elements import (
    emit_end,
    emit_gateway,
    emit_sequence_flow,
    emit_service_task,
    emit_start,
    emit_user_task,
)
from app.bpmn.ir import IRError, ProcessIR
from app.bpmn.layout import LayoutModel


def _escape(value: str | None) -> str:
    """XML-escape a string value."""
    if value is None:
        return ""
    return saxutils.escape(str(value))


def emit_bpmn(process_ir: ProcessIR, layout_model: LayoutModel) -> str:
    """Assemble and return one complete BPMN 2.0 XML document as a string.

    The output uses ``\\n`` newlines, two-space indent, a trailing newline,
    and every injected value is XML-escaped so the result is byte-stable.
    """
    shapes_by_step = {shape.step_key: shape for shape in layout_model.shapes}
    edges_by_flow = {edge.flow_key: edge for edge in layout_model.edges}

    sorted_steps = sorted(process_ir.steps, key=lambda s: (s.ordinal, s.step_key))
    sorted_flows = sorted(
        process_ir.flows,
        key=lambda f: (not f.is_default, f.flow_key),
    )

    default_flow_id = ""
    for flow in process_ir.flows:
        if flow.is_default:
            default_flow_id = flow.flow_key
            break

    pk = _escape(process_ir.process_key)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:omgdc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:omgdi="http://www.omg.org/spec/DD/20100524/DI" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:flowable="http://flowable.org/bpmn" '
        'targetNamespace="http://bpmn.io/schema/bpmn">',
        f'  <bpmn:process id="{pk}" isExecutable="true">',
    ]

    for step in sorted_steps:
        stype = step.step_type
        # NOTE: these step_type values are the canonical vocabulary shared by
        # app.bpmn.ir, app.bpmn.svg_emit and the wizard. They are NOT the BPMN
        # element names (userTask/serviceTask/exclusiveGateway) — mapping them
        # here is what emit_*() does. Keep them in lock-step with ir.py/svg_emit.
        if stype == "start":
            frag = emit_start(step.step_key)
        elif stype == "end":
            frag = emit_end(step.step_key)
        elif stype == "user":
            frag = emit_user_task(
                id=step.step_key,
                name=_escape(step.name),
                candidate_groups=step.candidate_groups or [],
                form_key=step.form_key,
            )
        elif stype == "service":
            frag = emit_service_task(
                id=step.step_key,
                name=_escape(step.name),
                service_impl=step.service_impl or "",
            )
        elif stype == "gateway":
            frag = emit_gateway(
                id=step.step_key,
                name=_escape(step.name),
                default_flow_id=default_flow_id,
            )
        else:
            # Fail closed: silently skipping an unknown step_type is exactly what
            # let the *_task/exclusive_gateway drift ship malformed BPMN — the DI
            # section and sequence flows still reference the dropped node, leaving
            # dangling sourceRef/targetRef. Raise so the drift can never be silent.
            raise IRError(f"Step {step.step_key!r} has unsupported step_type {stype!r}")

        for line in frag.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(f"    {stripped}")

    for flow in sorted_flows:
        frag = emit_sequence_flow(
            id=flow.flow_key,
            source_ref=flow.source_step,
            target_ref=flow.target_step,
            condition=_escape(flow.condition_expression),
        )
        for line in frag.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(f"    {stripped}")

    lines.append("  </bpmn:process>")
    lines.append("  <bpmndi:BPMNDiagram>")
    lines.append(f'    <bpmndi:BPMNPlane bpmnElement="{pk}">')

    for step in sorted_steps:
        shape = shapes_by_step.get(step.step_key)
        if shape is None:
            continue
        sk = _escape(step.step_key)
        lines.append(f'      <bpmndi:BPMNShape bpmnElement="{sk}">')
        lines.append(
            f'        <omgdc:Bounds x="{shape.x}" y="{shape.y}" '
            f'width="{shape.w}" height="{shape.h}"/>'
        )
        lines.append("      </bpmndi:BPMNShape>")

    for flow in sorted_flows:
        edge = edges_by_flow.get(flow.flow_key)
        if edge is None:
            continue
        fk = _escape(flow.flow_key)
        lines.append(f'      <bpmndi:BPMNEdge bpmnElement="{fk}">')
        for wp in edge.waypoints:
            lines.append(f'        <omgdi:waypoint x="{wp[0]}" y="{wp[1]}"/>')
        lines.append("      </bpmndi:BPMNEdge>")

    lines.append("    </bpmndi:BPMNPlane>")
    lines.append("  </bpmndi:BPMNDiagram>")
    lines.append("</bpmn:definitions>")

    return "\n".join(lines) + "\n"
