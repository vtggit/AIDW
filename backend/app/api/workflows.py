"""workflows workflow proxy endpoints (engine-generated: sidecar-proxy lane)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.workflows import flowable_client as _sidecar

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class RtbfStartBody(BaseModel):
    """Opaque references ONLY (AIDW#189 OQ-6). extra="forbid" makes any
    unknown variable name a 422 at the boundary — the server-side allowlist."""

    model_config = {"extra": "forbid"}

    dsr_request_id: str = Field(min_length=1, max_length=128)


@router.post("/rtbf/start", status_code=202)
async def post_rtbf_start(
    body: RtbfStartBody,
    _user: AuthUser = Depends(require_authenticated_user),
):
    try:
        instance_id = await _sidecar.start_process("aidwRtbf", body.model_dump())
    except _sidecar.SidecarConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="workflow engine unreachable")
    return {"instance_id": instance_id, "process_key": "aidwRtbf"}


@router.get("/instances/{instance_id}")
async def get_instances(
    instance_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
):
    if len(instance_id) > 64:
        raise HTTPException(status_code=422, detail="invalid instance reference")
    try:
        data = await _sidecar.get_instance(instance_id)
    except _sidecar.SidecarConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="workflow engine unreachable")
    if data is None:
        raise HTTPException(status_code=404, detail="workflow instance not found")
    return {
        "instance_id": data.get("id"),
        # Flowable historic instances return processDefinitionKey=None; the key is
        # the first colon-segment of processDefinitionId (AIDW#192 deploy-wire).
        "process_key": (
            data.get("processDefinitionKey")
            or (data.get("processDefinitionId") or "").split(":")[0]
            or None
        ),
        "ended": data.get("endTime") is not None,
    }
