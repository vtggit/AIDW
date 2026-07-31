"""SequenceRunStep API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.sequence_run_steps import (
    SequenceRunStepCreate,
    SequenceRunStepResponse,
    SequenceRunStepUpdate,
)
from app.repositories.sequence_run_steps_postgres_repository import (
    SequenceRunStepPostgresRepository,
)
from app.services.sequence_run_steps_service import SequenceRunStepService

router = APIRouter(prefix="/api/sequence-run-steps", tags=["sequence-run-steps"])

_repository = SequenceRunStepPostgresRepository()
_service = SequenceRunStepService(repository=_repository)


def get_service() -> SequenceRunStepService:
    return _service


@router.get("", response_model=list[SequenceRunStepResponse])
def list_sequence_run_steps(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceRunStepService = Depends(get_service),
):
    return service.list_sequence_run_steps()


@router.post(
    "", response_model=SequenceRunStepResponse, status_code=status.HTTP_201_CREATED
)
def create_sequence_run_step(
    payload: SequenceRunStepCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunStepService = Depends(get_service),
):
    return service.create_sequence_run_step(payload)


@router.get("/{entity_id}", response_model=SequenceRunStepResponse)
def get_sequence_run_step(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceRunStepService = Depends(get_service),
):
    entity = service.get_sequence_run_step(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceRunStep '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SequenceRunStepResponse)
def update_sequence_run_step(
    entity_id: str,
    payload: SequenceRunStepUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunStepService = Depends(get_service),
):
    entity = service.update_sequence_run_step(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceRunStep '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence_run_step(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceRunStepService = Depends(get_service),
):
    if not service.delete_sequence_run_step(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceRunStep '{entity_id}' not found.",
        )
