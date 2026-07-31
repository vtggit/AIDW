"""Service for projecting load sequences as BPMN diagrams."""

from app.bpmn.ir import build_ir
from app.bpmn.layout import layout
from app.bpmn.svg_emit import emit_svg
from app.bpmn.xml_emit import emit_bpmn
from app.db.connection import get_cursor


def project_load_sequence_to_bpmn(sequence_id: str) -> dict | None:
    """Project a load sequence's ordered steps as a BPMN diagram.

    Returns ``None`` if the sequence does not exist, otherwise returns
    ``{"process_key", "bpmn_xml", "svg"}``.  Raises ``IRError`` on invalid IR.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM load_sequences WHERE id = %s",
            (sequence_id,),
        )
        seq_row = cur.fetchone()
        if seq_row is None:
            return None

        cur.execute(
            "SELECT * FROM sequence_steps WHERE sequence_id = %s ORDER BY order_index ASC",
            (sequence_id,),
        )
        step_rows = [dict(r) for r in cur.fetchall()]

    process_key = f"load_sequence_{sequence_id}"
    seq_name = seq_row.get("name") or ""

    steps: list[dict] = []
    flows: list[dict] = []

    # Synthetic start step (ordinal 0)
    steps.append(
        {
            "step_key": "start",
            "ordinal": 0,
            "step_type": "start",
            "name": None,
            "service_impl": None,
            "candidate_groups": None,
            "form_key": None,
        }
    )

    # One service step per row — 1-based position for step_key and ordinal.
    for idx, row in enumerate(step_rows):
        position = idx + 1
        label = row.get("label")
        name = label if label else (row.get("name") or "")
        steps.append(
            {
                "step_key": f"step_{position}",
                "ordinal": position,
                "step_type": "service",
                "name": name,
                "service_impl": "${loadSequenceStep}",
                "candidate_groups": None,
                "form_key": None,
            }
        )

    # Synthetic end step (ordinal N+1)
    end_ordinal = len(step_rows) + 1
    steps.append(
        {
            "step_key": "end",
            "ordinal": end_ordinal,
            "step_type": "end",
            "name": None,
            "service_impl": None,
            "candidate_groups": None,
            "form_key": None,
        }
    )

    # Flows chain: start -> step_1 -> ... -> step_N -> end.
    flow_sources = ["start"] + [f"step_{i+1}" for i in range(len(step_rows))]
    flow_targets = [f"step_{i+1}" for i in range(len(step_rows))] + ["end"]

    for idx, (src, tgt) in enumerate(zip(flow_sources, flow_targets)):
        flows.append(
            {
                "flow_key": f"flow_{idx}",
                "source_step": src,
                "target_step": tgt,
                "condition_expression": None,
                "is_default": False,
            }
        )

    process = {
        "process_key": process_key,
        "name": seq_name,
        "version": 1,
    }

    process_ir = build_ir(process, steps, flows)
    layout_model = layout(process_ir)
    bpmn_xml = emit_bpmn(process_ir, layout_model)
    svg = emit_svg(process_ir, layout_model)

    return {
        "process_key": process_ir.process_key,
        "bpmn_xml": bpmn_xml,
        "svg": svg,
    }
