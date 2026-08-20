"""SequenceRun API routes."""

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.sequence_runs import (
    SequenceRunCreate,
    SequenceRunResponse,
    SequenceRunUpdate,
)
from app.repositories.sequence_runs_postgres_repository import (
    SequenceRunPostgresRepository,
)
from app.services.sequence_execution_service import execute_sequence_run
from app.services.sequence_runs_service import SequenceRunService

router = APIRouter(prefix="/api/sequence-runs", tags=["sequence-runs"])

_repository = SequenceRunPostgresRepository()
_service = SequenceRunService(repository=_repository)


def get_service() -> SequenceRunService:
    return _service


@router.get("", response_model=list[SequenceRunResponse])
def list_sequence_runs(
    limit: int | None = None,
    offset: int | None = None,
    status: str | None = None,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceRunService = Depends(get_service),
    response: Response = None,
):
    # Pagination contract: limit must be within 1..100 and offset must be >= 0.
    # A violation is a client error (422) that names the offending parameter.
    if limit is not None and (limit < 1 or limit > 100):
        raise HTTPException(
            status_code=422,
            detail="Invalid value for parameter 'limit': must be between 1 and 100.",
        )
    if offset is not None and offset < 0:
        raise HTTPException(
            status_code=422,
            detail="Invalid value for parameter 'offset': must be 0 or greater.",
        )
    if status is not None:
        all_runs = service.list_sequence_runs()
        matched = [r for r in all_runs if r.get("status") == status]
        # X-Total-Count reflects the FILTERED total, before the window is applied.
        if response is not None:
            response.headers["X-Total-Count"] = str(len(matched))
        if offset is not None:
            matched = matched[offset:]
        if limit is not None:
            matched = matched[:limit]
        return matched
    # Unfiltered list: X-Total-Count is the unfiltered total, before the window.
    all_runs = service.list_sequence_runs()
    if response is not None:
        response.headers["X-Total-Count"] = str(len(all_runs))
    if offset is not None:
        all_runs = all_runs[offset:]
    if limit is not None:
        all_runs = all_runs[:limit]
    return all_runs


@router.post("", response_model=SequenceRunResponse, status_code=201)
def create_sequence_run(
    payload: SequenceRunCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunService = Depends(get_service),
):
    return service.create_sequence_run(payload)


@router.get("/{entity_id}", response_model=SequenceRunResponse)
def get_sequence_run(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceRunService = Depends(get_service),
):
    entity = service.get_sequence_run(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"SequenceRun '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SequenceRunResponse)
def update_sequence_run(
    entity_id: str,
    payload: SequenceRunUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunService = Depends(get_service),
):
    entity = service.update_sequence_run(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"SequenceRun '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=204)
def delete_sequence_run(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunService = Depends(get_service),
):
    if not service.delete_sequence_run(entity_id):
        raise HTTPException(
            status_code=404,
            detail=f"SequenceRun '{entity_id}' not found.",
        )


@router.post("/{run_id}/execute")
def execute_run(
    run_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Execute a pending sequence run.

    Processes steps in order, recording per-step state. Returns 200 with the
    final run state even if steps failed. Returns 409 if the run is not pending.
    """
    try:
        return execute_sequence_run(run_id)
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        # Should not happen, but catch any unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error executing run: {str(exc)}",
        )
