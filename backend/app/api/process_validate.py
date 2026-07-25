"""Validate a proposed delta over a process definition without persisting anything."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.bpmn.ir import IRError, build_ir
from app.bpmn.layout import layout
from app.bpmn.svg_emit import emit_svg
from app.bpmn.xml_emit import emit_bpmn
from app.db.connection import get_cursor
from app.observability.logging import get_request_id

router = APIRouter(prefix="/api/process-definitions", tags=["process-validate"])


def _split_groups(value):
    """The candidate_groups column is a single VARCHAR; the ir contract wants list[str] | None."""
    if not value:
        return None
    groups = [g.strip() for g in str(value).split(",") if g.strip()]
    return groups or None


def _int_version(value):
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else 1


class StepDelta(BaseModel):
    step_key: str
    name: str | None = None
    ordinal: int
    step_type: str
    service_impl: str | None = None
    candidate_groups: list[str] | None = None
    form_key: str | None = None


class FlowDelta(BaseModel):
    flow_key: str
    source_step: str
    target_step: str
    condition_expression: str | None = None
    is_default: bool = False


class ValidateRequest(BaseModel):
    add_steps: list[StepDelta] = Field(default_factory=list)
    add_flows: list[FlowDelta] = Field(default_factory=list)
    remove_step_keys: list[str] = Field(default_factory=list)
    remove_flow_keys: list[str] = Field(default_factory=list)


@router.post("/{definition_id}/validate")
def validate_process_delta(
    definition_id: str,
    body: ValidateRequest,
    _user: AuthUser = Depends(require_authenticated_user),
):
    """Validate a proposed delta against the current process-definition rows.

    Nothing is persisted — only SELECT queries are issued.  On success the full
    BPMN XML and SVG are returned; on validation failure a 422 envelope with the
    IRError messages is sent back.
    """
    # ---- Size guard --------------------------------------------------------
    total_additions = len(body.add_steps) + len(body.add_flows)
    if total_additions > 200:
        request_id = get_request_id()
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Delta too large: {total_additions} additions (limit is 200)",
                "errors": [f"Too many items in delta ({total_additions} > 200)"],
                "request_id": request_id or "",
            },
        )

    # ---- Load current rows -------------------------------------------------
    with get_cursor() as cur:
        cur.execute("SELECT * FROM process_definitions WHERE id = %s", (definition_id,))
        definition = cur.fetchone()
        if definition is None:
            request_id = get_request_id()
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "process definition not found",
                    "request_id": request_id or "",
                },
            )

        cur.execute(
            "SELECT * FROM process_steps WHERE process_definition_id = %s ORDER BY ordinal, step_key",
            (definition_id,),
        )
        step_rows = cur.fetchall()

        cur.execute(
            "SELECT * FROM sequence_flows WHERE process_definition_id = %s ORDER BY flow_key",
            (definition_id,),
        )
        flow_rows = cur.fetchall()

    # ---- Adapt rows to IR contract -----------------------------------------
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

    # ---- Apply delta in memory ---------------------------------------------
    remove_steps = set(body.remove_step_keys)
    remove_flows = set(body.remove_flow_keys)

    steps = [s for s in steps if s["step_key"] not in remove_steps]
    flows = [f for f in flows if f["flow_key"] not in remove_flows]

    # Convert Pydantic models to dicts for the IR builder
    added_steps = [s.model_dump() for s in body.add_steps]
    added_flows = [f.model_dump() for f in body.add_flows]

    steps.extend(added_steps)
    flows.extend(added_flows)

    # ---- Run pipeline ------------------------------------------------------
    try:
        process_ir = build_ir(process, steps, flows)
        layout_model = layout(process_ir)
        bpmn_xml = emit_bpmn(process_ir, layout_model)
        svg = emit_svg(process_ir, layout_model)
    except IRError as exc:
        request_id = get_request_id()
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Validation failed: {exc}",
                "errors": [str(exc)],
                "request_id": request_id or "",
            },
        )

    return {
        "valid": True,
        "bpmn_xml": bpmn_xml,
        "svg": svg,
    }
