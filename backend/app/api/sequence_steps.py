"""SequenceStep API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.sequence_steps import (
    SequenceStepCreate,
    SequenceStepResponse,
    SequenceStepUpdate,
)
from app.repositories.sequence_steps_postgres_repository import (
    SequenceStepPostgresRepository,
)
from app.services.sequence_steps_service import SequenceStepService

router = APIRouter(prefix="/api/sequence-steps", tags=["sequence-steps"])

_repository = SequenceStepPostgresRepository()
_service = SequenceStepService(repository=_repository)


def get_service() -> SequenceStepService:
    return _service


@router.get("", response_model=list[SequenceStepResponse])
def list_sequence_steps(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceStepService = Depends(get_service),
):
    return service.list_sequence_steps()


@router.post(
    "", response_model=SequenceStepResponse, status_code=status.HTTP_201_CREATED
)
def create_sequence_step(
    payload: SequenceStepCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceStepService = Depends(get_service),
):
    return service.create_sequence_step(payload)


@router.get("/{entity_id}", response_model=SequenceStepResponse)
def get_sequence_step(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceStepService = Depends(get_service),
):
    entity = service.get_sequence_step(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceStep '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SequenceStepResponse)
def update_sequence_step(
    entity_id: str,
    payload: SequenceStepUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceStepService = Depends(get_service),
):
    entity = service.update_sequence_step(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceStep '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence_step(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceStepService = Depends(get_service),
):
    if not service.delete_sequence_step(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceStep '{entity_id}' not found.",
        )
