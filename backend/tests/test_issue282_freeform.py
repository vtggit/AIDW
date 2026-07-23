"""Proving test for Issue #282 — CDC refresh process seed & BPMN assembly."""

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.svg_emit import emit_svg
from app.bpmn.xml_emit import emit_bpmn
from app.db.connection import get_cursor


def test_issue282_freeform():
    with get_cursor() as cur:
        # Verify definition row exists with correct key and status
        cur.execute(
            "SELECT * FROM process_definitions WHERE id = %s", ("sysproc-cdc-refresh",)
        )
        def_row = cur.fetchone()
        assert def_row is not None, "CDC refresh process definition missing"
        assert def_row["process_key"] == "cdc_refresh"
        assert def_row["status"] == "system"

        # Verify exactly 9 steps (idempotency check — not doubled)
        cur.execute(
            "SELECT * FROM process_steps WHERE process_definition_id = %s",
            ("sysproc-cdc-refresh",),
        )
        step_rows = cur.fetchall()
        assert len(step_rows) == 9, f"Expected 9 steps, got {len(step_rows)}"

        # Verify exactly 8 flows (idempotency check — not doubled)
        cur.execute(
            "SELECT * FROM sequence_flows WHERE process_definition_id = %s",
            ("sysproc-cdc-refresh",),
        )
        flow_rows = cur.fetchall()
        assert len(flow_rows) == 8, f"Expected 8 flows, got {len(flow_rows)}"

    # Assemble dicts exactly as backend/app/api/process_generate.py does
    process_dict = {
        "process_key": def_row["process_key"],
        "name": def_row["name"],
        "version": int(def_row["version"]),
    }

    steps_dicts = []
    for s in step_rows:
        cg = s.get("candidate_groups")
        steps_dicts.append(
            {
                "step_key": s["step_key"],
                "ordinal": s["ordinal"],
                "step_type": s["step_type"],
                "name": s["name"],
                "service_impl": s["service_impl"],
                "candidate_groups": list(cg) if cg else [],
                "form_key": s.get("form_key"),
            }
        )

    flows_dicts = []
    for f in flow_rows:
        flows_dicts.append(
            {
                "flow_key": f["flow_key"],
                "source_step": f["source_step"],
                "target_step": f["target_step"],
                "condition_expression": f["condition_expression"],
                "is_default": f["is_default"],
            }
        )

    # Build IR and layout model
    ir = build_ir(process_dict, steps_dicts, flows_dicts)
    layout_model = layout(ir)

    # Emit BPMN XML and assert required elements & delegate expressions
    bpmn_xml = emit_bpmn(ir, layout_model)
    assert "bpmn:startEvent" in bpmn_xml
    assert "bpmn:exclusiveGateway" in bpmn_xml
    for expr in (
        "${contextLoader}",
        "${sourcePageFetcher}",
        "${rowsApplier}",
        "${runFailer}",
        "${runFinalizer}",
    ):
        assert expr in bpmn_xml, f"Missing delegate expression {expr}"

    # Emit SVG and assert root element (after optional XML declaration) is <svg
    svg_str = emit_svg(ir, layout_model)
    clean_svg = svg_str.strip()
    if clean_svg.startswith("<?xml"):
        clean_svg = clean_svg.split("?>", 1)[1].strip()
    assert clean_svg.startswith(
        "<svg"
    ), f"SVG does not start with <svg: {clean_svg[:50]}"
