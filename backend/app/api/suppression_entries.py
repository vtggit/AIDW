"""SuppressionEntry API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.suppression_entries import (
    SuppressionEntryCreate,
    SuppressionEntryResponse,
    SuppressionEntryUpdate,
)
from app.repositories.suppression_entries_postgres_repository import (
    SuppressionEntryPostgresRepository,
)
from app.services.suppression_entries_service import SuppressionEntryService

router = APIRouter(prefix="/api/suppression-entries", tags=["suppression-entries"])

_repository = SuppressionEntryPostgresRepository()
_service = SuppressionEntryService(repository=_repository)


def get_service() -> SuppressionEntryService:
    return _service


@router.get("", response_model=list[SuppressionEntryResponse])
def list_suppression_entries(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SuppressionEntryService = Depends(get_service),
):
    return service.list_suppression_entries()


@router.post(
    "", response_model=SuppressionEntryResponse, status_code=status.HTTP_201_CREATED
)
def create_suppression_entry(
    payload: SuppressionEntryCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuppressionEntryService = Depends(get_service),
):
    return service.create_suppression_entry(payload)


@router.get("/{entity_id}", response_model=SuppressionEntryResponse)
def get_suppression_entry(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SuppressionEntryService = Depends(get_service),
):
    entity = service.get_suppression_entry(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuppressionEntry '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SuppressionEntryResponse)
def update_suppression_entry(
    entity_id: str,
    payload: SuppressionEntryUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuppressionEntryService = Depends(get_service),
):
    entity = service.update_suppression_entry(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuppressionEntry '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suppression_entry(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuppressionEntryService = Depends(get_service),
):
    if not service.delete_suppression_entry(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuppressionEntry '{entity_id}' not found.",
        )
