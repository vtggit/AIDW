"""Proving test for Issue #280 — RTBF Erasure process seed & BPMN assembly."""

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.svg_emit import emit_svg
from app.bpmn.xml_emit import emit_bpmn
from app.db.connection import get_cursor


def test_issue280_freeform():
    with get_cursor() as cur:
        # Verify definition exists
        cur.execute(
            "SELECT * FROM process_definitions WHERE id = %s", ("sysproc-rtbf-erasure",)
        )
        def_row = cur.fetchone()
        assert def_row is not None, "Process definition sysproc-rtbf-erasure missing"
        assert def_row["process_key"] == "rtbf_erasure"
        assert def_row["status"] == "system"

        # Verify steps count (idempotency check)
        cur.execute(
            "SELECT * FROM process_steps WHERE process_definition_id = %s",
            ("sysproc-rtbf-erasure",),
        )
        step_rows = cur.fetchall()
        assert len(step_rows) == 8, f"Expected 8 steps, got {len(step_rows)}"

        # Verify flows count (idempotency check)
        cur.execute(
            "SELECT * FROM sequence_flows WHERE process_definition_id = %s",
            ("sysproc-rtbf-erasure",),
        )
        flow_rows = cur.fetchall()
        assert len(flow_rows) == 7, f"Expected 7 flows, got {len(flow_rows)}"

    # Assemble dicts exactly as process_generate.py does
    process_dict = {
        "process_key": def_row["process_key"],
        "name": def_row["name"],
        "version": int(def_row["version"]),
    }

    steps_dicts = [
        {
            "step_key": row["step_key"],
            "ordinal": row["ordinal"],
            "step_type": row["step_type"],
            "name": row["name"],
            "service_impl": row["service_impl"],
            "candidate_groups": list(row.get("candidate_groups") or []),
            "form_key": row.get("form_key"),
        }
        for row in step_rows
    ]

    flows_dicts = [
        {
            "flow_key": row["flow_key"],
            "source_step": row["source_step"],
            "target_step": row["target_step"],
            "condition_expression": row.get("condition_expression"),
            "is_default": row["is_default"],
        }
        for row in flow_rows
    ]

    # Build IR
    process_ir = build_ir(process_dict, steps_dicts, flows_dicts)

    # Layout
    layout_model = layout(process_ir)

    # Emit BPMN and verify content
    bpmn_xml = emit_bpmn(process_ir, layout_model)
    assert "bpmn:startEvent" in bpmn_xml
    assert "bpmn:exclusiveGateway" in bpmn_xml
    assert "${recordEraser}" in bpmn_xml
    assert "${profileScrubber}" in bpmn_xml
    assert "${suppressionWriter}" in bpmn_xml
    assert "${requestFinalizer}" in bpmn_xml

    # Emit SVG and verify root element
    svg_str = emit_svg(process_ir, layout_model)
    stripped = svg_str.strip()
    if stripped.startswith("<?xml"):
        stripped = stripped[stripped.index("?>") + 2 :].strip()
    assert stripped.startswith("<svg"), f"SVG does not start with <svg: {stripped[:50]}"
