"""Ingest endpoint: POST /api/pipelines/{pipeline_id}/runs.

Two executor modes (INGEST_EXECUTOR, doc §1 API⊥worker):
- ``inline`` (default): the interim in-API executor — requires ENABLE_INAPI_EGRESS, executes one
  cursor-ingest run synchronously and returns the finished run (201). A fetch failure still
  returns 201 — the created run carries status=failed and the error detail, which IS the
  observable record of the attempt.
- ``worker``: the API only validates and enqueues a ``pending`` run (202, no egress from the
  API process); the connector/ingestion worker (``python -m app.worker``) claims and executes it,
  writing IDENTICAL rows.
Admin-only; 404 unknown pipeline, 422 failed preconditions — in both modes, checked before any
run row exists.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.config import ENABLE_INAPI_EGRESS, INGEST_EXECUTOR
from app.ingest.service import IngestError, create_pending_run, start_run

router = APIRouter(prefix="/api/pipelines", tags=["ingest"])


@router.post("/{pipeline_id}/runs", status_code=status.HTTP_201_CREATED)
def run_pipeline(
    pipeline_id: str, response: Response, _user=Depends(require_role(ROLE_ADMIN))
):
    try:
        if INGEST_EXECUTOR == "worker":
            body = create_pending_run(pipeline_id)
            response.status_code = status.HTTP_202_ACCEPTED
            return body
        if not ENABLE_INAPI_EGRESS:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "in-API ingest is disabled (set ENABLE_INAPI_EGRESS=true to enable the "
                "interim in-API egress path, or INGEST_EXECUTOR=worker to enqueue for the "
                "connector worker)",
            )
        return start_run(pipeline_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pipeline not found")
    except IngestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
