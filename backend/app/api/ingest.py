"""Ingest endpoint: POST /api/pipelines/{pipeline_id}/runs.

Executes one cursor-ingest run of a pipeline (interim in-API egress): build the watermark page
URL, fetch + map rows, upsert the CDC op-log, advance the delta cursor, and fire the §6 automatic
profile + re-score pass. Gated by ENABLE_INAPI_EGRESS (default off) like discovery/profiling;
admin-only. A fetch failure still returns 201 — the created run carries status=failed and the
error detail, which IS the observable record of the attempt.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.config import ENABLE_INAPI_EGRESS
from app.ingest.service import IngestError, start_run

router = APIRouter(prefix="/api/pipelines", tags=["ingest"])


@router.post("/{pipeline_id}/runs", status_code=status.HTTP_201_CREATED)
def run_pipeline(pipeline_id: str, _user=Depends(require_role(ROLE_ADMIN))):
    if not ENABLE_INAPI_EGRESS:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "in-API ingest is disabled (set ENABLE_INAPI_EGRESS=true to enable the interim "
            "in-API egress path)",
        )
    try:
        return start_run(pipeline_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pipeline not found")
    except IngestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
