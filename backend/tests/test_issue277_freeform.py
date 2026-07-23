"""Proving test for Issue #277 — accept-suggestion system process seed."""

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.svg_emit import emit_svg
from app.bpmn.xml_emit import emit_bpmn
from app.db.connection import get_cursor


def test_issue277_freeform():
    """Assert the seeded accept-suggestion process exists, is idempotent, and forms a valid diagram."""

    # Fetch the definition row
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM process_definitions WHERE process_key = %s",
            ("accept_suggestion",),
        )
        rows = list(cur)

    assert len(rows) == 1, f"Expected exactly 1 definition row, got {len(rows)}"
    definition = rows[0]
    assert definition["process_key"] == "accept_suggestion"
    assert definition["status"] == "system"
    process_definition_id = definition["id"]

    # Fetch steps and flows for this process definition
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM process_steps WHERE process_definition_id = %s ORDER BY ordinal",
            (process_definition_id,),
        )
        step_rows = list(cur)

        cur.execute(
            "SELECT * FROM sequence_flows WHERE process_definition_id = %s",
            (process_definition_id,),
        )
        flow_rows = list(cur)

    # Assert exactly 6 steps and 5 flows (proving idempotency — not doubled)
    assert len(step_rows) == 6, f"Expected 6 steps, got {len(step_rows)}"
    assert len(flow_rows) == 5, f"Expected 5 flows, got {len(flow_rows)}"

    # Build dicts matching what process_generate.py assembles
    process = {
        "process_key": definition["process_key"],
        "name": definition["name"],
        "version": int(definition["version"]),
    }

    steps = []
    for row in step_rows:
        steps.append(
            {
                "step_key": row["step_key"],
                "ordinal": int(row["ordinal"]),
                "step_type": row["step_type"],
                "name": row["name"],
                "service_impl": row["service_impl"],
                "candidate_groups": [],
                "form_key": None,
            }
        )

    flows = []
    for row in flow_rows:
        flows.append(
            {
                "flow_key": row["flow_key"],
                "source_step": row["source_step"],
                "target_step": row["target_step"],
                "condition_expression": row["condition_expression"],
                "is_default": bool(row["is_default"]),
            }
        )

    # Assert build_ir succeeds
    process_ir = build_ir(process, steps, flows)
    assert process_ir is not None

    # Layout the diagram
    layout_model = layout(process_ir)
    assert layout_model is not None

    # Emit BPMN and verify expected elements
    bpmn_xml = emit_bpmn(process_ir, layout_model)
    assert isinstance(bpmn_xml, str), "emit_bpmn should return a string"
    assert "bpmn:startEvent" in bpmn_xml, "BPMN should contain startEvent"
    assert "bpmn:exclusiveGateway" in bpmn_xml, "BPMN should contain exclusiveGateway"
    assert (
        "${suggestionLookupDelegate}" in bpmn_xml
    ), "BPMN should contain suggestionLookupDelegate expression"
    assert (
        "${dashboardItemCreatorDelegate}" in bpmn_xml
    ), "BPMN should contain dashboardItemCreatorDelegate expression"

    # Emit SVG and verify root element
    svg_str = emit_svg(process_ir, layout_model)
    assert isinstance(svg_str, str), "emit_svg should return a string"
    svg_stripped = svg_str.strip()
    if svg_stripped.startswith("<?xml"):
        svg_content = svg_stripped[svg_stripped.index("?>") + 2 :].strip()
    else:
        svg_content = svg_stripped
    assert svg_content.startswith(
        "<svg"
    ), f"SVG root should be <svg, got: {svg_content[:50]}"
