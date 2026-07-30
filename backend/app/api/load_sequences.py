"""LoadSequence API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.load_sequences import (
    LoadSequenceCreate,
    LoadSequenceResponse,
    LoadSequenceUpdate,
)
from app.repositories.load_sequences_postgres_repository import (
    LoadSequencePostgresRepository,
)
from app.services.load_sequences_service import LoadSequenceService

router = APIRouter(prefix="/api/load-sequences", tags=["load-sequences"])

_repository = LoadSequencePostgresRepository()
_service = LoadSequenceService(repository=_repository)


def get_service() -> LoadSequenceService:
    return _service


@router.get("", response_model=list[LoadSequenceResponse])
def list_load_sequences(
    _user: AuthUser = Depends(require_authenticated_user),
    service: LoadSequenceService = Depends(get_service),
):
    return service.list_load_sequences()


@router.post(
    "", response_model=LoadSequenceResponse, status_code=status.HTTP_201_CREATED
)
def create_load_sequence(
    payload: LoadSequenceCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LoadSequenceService = Depends(get_service),
):
    return service.create_load_sequence(payload)


@router.get("/{entity_id}", response_model=LoadSequenceResponse)
def get_load_sequence(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: LoadSequenceService = Depends(get_service),
):
    entity = service.get_load_sequence(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=LoadSequenceResponse)
def update_load_sequence(
    entity_id: str,
    payload: LoadSequenceUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LoadSequenceService = Depends(get_service),
):
    entity = service.update_load_sequence(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_load_sequence(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LoadSequenceService = Depends(get_service),
):
    if not service.delete_load_sequence(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{entity_id}' not found.",
        )
