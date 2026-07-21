"""SVG emission for BPMN process IR + layout model."""

from __future__ import annotations

import xml.sax.saxutils as saxutils

from app.bpmn.ir import ProcessIR
from app.bpmn.layout import LayoutModel


def emit_svg(process_ir: ProcessIR, layout_model: LayoutModel) -> str:
    """Assemble a complete, deterministic standalone SVG document.

    The document begins with an XML declaration; then an ``<svg>`` root
    declaring the SVG namespace, ``width``/``height`` taken from the
    layout model's overall extent, and a matching ``viewBox``.

    Children are emitted in fixed order:
        1. Steps sorted by ``(ordinal, step_key)`` — each produces one
           shape element followed by one text label.
        2. Sequences sorted by ``(is_default first, then flow_key)`` —
           each produces one ``<polyline>``.

    Every line uses ``"\\n"`` newlines, a two-space indent, and the
    output ends with a trailing newline. All injected values are
    XML-escaped so the output is byte-stable.
    """
    lines: list[str] = []

    # --- compute overall extent from shapes + edge waypoints ----------
    max_x = 0
    max_y = 0
    for shape in layout_model.shapes:
        if shape.x + shape.w > max_x:
            max_x = shape.x + shape.w
        if shape.y + shape.h > max_y:
            max_y = shape.y + shape.h
    for edge in layout_model.edges:
        for wx, wy in edge.waypoints:
            if wx > max_x:
                max_x = wx
            if wy > max_y:
                max_y = wy

    width = max_x
    height = max_y

    # --- XML declaration + root svg -----------------------------------
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )

    # --- shape lookup -------------------------------------------------
    shapes_by_key = {s.step_key: s for s in layout_model.shapes}

    # --- steps (sorted by ordinal, step_key) --------------------------
    sorted_steps = sorted(process_ir.steps, key=lambda s: (s.ordinal, s.step_key))
    for step in sorted_steps:
        shape = shapes_by_key[step.step_key]
        x = shape.x
        y = shape.y
        w = shape.w
        h = shape.h
        cx = x + w // 2
        cy = y + h // 2

        escaped_name = saxutils.escape(step.name or "")
        step_id = saxutils.escape(step.step_key)

        if step.step_type in ("start", "end"):
            r = min(w, h) // 2
            lines.append(
                f'  <circle cx="{cx}" cy="{cy}" r="{r}" ' f'id="shape-{step_id}"/>'
            )
        elif step.step_type == "gateway":
            top = (x, y)
            right = (x + w, y + h // 2)
            bottom = (x, y + h)
            left = (x, y + h // 2)
            pts = (
                f"{top[0]},{top[1]} {right[0]},{right[1]} "
                f"{bottom[0]},{bottom[1]} {left[0]},{left[1]}"
            )
            lines.append(f'  <polygon points="{pts}" id="shape-{step_id}"/>')
        else:
            # task (and any other type) -> rect
            lines.append(
                f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'id="shape-{step_id}"/>'
            )

        lines.append(
            f'  <text x="{cx}" y="{cy}" text-anchor="middle" '
            f'dominant-baseline="central">{escaped_name}</text>'
        )

    # --- sequences (sorted: is_default first, then flow_key) ----------
    sorted_flows = sorted(
        process_ir.flows,
        key=lambda f: (not f.is_default, f.flow_key),
    )
    edges_by_key = {e.flow_key: e for e in layout_model.edges}

    for flow in sorted_flows:
        edge = edges_by_key[flow.flow_key]
        pts_str = " ".join(f"{wx},{wy}" for wx, wy in edge.waypoints)
        flow_id = saxutils.escape(flow.flow_key)
        lines.append(f'  <polyline points="{pts_str}" id="edge-{flow_id}"/>')

    lines.append("</svg>")
    return "\n".join(lines) + "\n"
