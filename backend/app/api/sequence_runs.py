"""SequenceRun API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

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
from app.services.sequence_runs_service import SequenceRunService

router = APIRouter(prefix="/api/sequence-runs", tags=["sequence-runs"])

_repository = SequenceRunPostgresRepository()
_service = SequenceRunService(repository=_repository)


def get_service() -> SequenceRunService:
    return _service


@router.get("", response_model=list[SequenceRunResponse])
def list_sequence_runs(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceRunService = Depends(get_service),
):
    return service.list_sequence_runs()


@router.post(
    "", response_model=SequenceRunResponse, status_code=status.HTTP_201_CREATED
)
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
            status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceRun '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence_run(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunService = Depends(get_service),
):
    if not service.delete_sequence_run(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceRun '{entity_id}' not found.",
        )
