"""Server-side BPMN generation (Path B Phase 3): Phase-1 rows -> deterministic BPMN 2.0 XML + SVG.

Reads a process_definition and its process_steps + sequence_flows, maps them onto the app.bpmn.ir
contract, and runs the frozen generator pipeline (build_ir -> layout -> emit_bpmn / emit_svg). One
LayoutModel drives both views, so the BPMN-DI and the SVG preview are byte-stable and can never
drift. No canvas -> no watermark.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.bpmn.ir import IRError, build_ir
from app.bpmn.layout import layout
from app.bpmn.svg_emit import emit_svg
from app.bpmn.xml_emit import emit_bpmn
from app.db.connection import get_cursor

router = APIRouter(prefix="/api/process-definitions", tags=["process-generate"])


def _split_groups(value):
    """The candidate_groups column is a single VARCHAR; the ir contract wants list[str] | None."""
    if not value:
        return None
    groups = [g.strip() for g in str(value).split(",") if g.strip()]
    return groups or None


def _int_version(value):
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else 1


@router.post("/{definition_id}/generate")
def generate_process_diagram(
    definition_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Generate the BPMN XML + SVG for one process definition's current rows."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM process_definitions WHERE id = %s", (definition_id,))
        definition = cur.fetchone()
        if definition is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="process definition not found"
            )
        cur.execute(
            "SELECT * FROM process_steps WHERE process_definition_id = %s "
            "ORDER BY ordinal, step_key",
            (definition_id,),
        )
        step_rows = cur.fetchall()
        cur.execute(
            "SELECT * FROM sequence_flows WHERE process_definition_id = %s ORDER BY flow_key",
            (definition_id,),
        )
        flow_rows = cur.fetchall()

    process = {
        "process_key": definition["process_key"],
        "name": definition["name"],
        "version": _int_version(definition["version"]),
    }
    steps = [
        {
            "step_key": r["step_key"],
            "ordinal": r["ordinal"],
            "step_type": r["step_type"],
            "name": r["name"],
            "service_impl": r["service_impl"],
            "candidate_groups": _split_groups(r["candidate_groups"]),
            "form_key": r["form_key"],
        }
        for r in step_rows
    ]
    flows = [
        {
            "flow_key": r["flow_key"],
            "source_step": r["source_step"],
            "target_step": r["target_step"],
            "condition_expression": r["condition_expression"],
            "is_default": bool(r["is_default"]),
        }
        for r in flow_rows
    ]

    try:
        process_ir = build_ir(process, steps, flows)
        layout_model = layout(process_ir)
        bpmn_xml = emit_bpmn(process_ir, layout_model)
        svg = emit_svg(process_ir, layout_model)
    except IRError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"process definition is not a valid diagram: {exc}",
        ) from exc

    return {
        "process_key": process_ir.process_key,
        "bpmn_xml": bpmn_xml,
        "svg": svg,
    }
