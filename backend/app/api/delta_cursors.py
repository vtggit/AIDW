"""DeltaCursor API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.delta_cursors import (
    DeltaCursorCreate,
    DeltaCursorResponse,
    DeltaCursorUpdate,
)
from app.repositories.delta_cursors_postgres_repository import (
    DeltaCursorPostgresRepository,
)
from app.services.delta_cursors_service import DeltaCursorService

router = APIRouter(prefix="/api/delta-cursors", tags=["delta-cursors"])

_repository = DeltaCursorPostgresRepository()
_service = DeltaCursorService(repository=_repository)


def get_service() -> DeltaCursorService:
    return _service


@router.get("", response_model=list[DeltaCursorResponse])
def list_delta_cursors(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DeltaCursorService = Depends(get_service),
):
    return service.list_delta_cursors()


@router.post(
    "", response_model=DeltaCursorResponse, status_code=status.HTTP_201_CREATED
)
def create_delta_cursor(
    payload: DeltaCursorCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeltaCursorService = Depends(get_service),
):
    return service.create_delta_cursor(payload)


@router.get("/{entity_id}", response_model=DeltaCursorResponse)
def get_delta_cursor(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DeltaCursorService = Depends(get_service),
):
    entity = service.get_delta_cursor(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeltaCursor '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DeltaCursorResponse)
def update_delta_cursor(
    entity_id: str,
    payload: DeltaCursorUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeltaCursorService = Depends(get_service),
):
    entity = service.update_delta_cursor(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeltaCursor '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_delta_cursor(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeltaCursorService = Depends(get_service),
):
    if not service.delete_delta_cursor(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeltaCursor '{entity_id}' not found.",
        )
