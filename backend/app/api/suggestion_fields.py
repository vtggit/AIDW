"""SuggestionField API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.suggestion_fields import (
    SuggestionFieldCreate,
    SuggestionFieldResponse,
    SuggestionFieldUpdate,
)
from app.repositories.suggestion_fields_postgres_repository import (
    SuggestionFieldPostgresRepository,
)
from app.services.suggestion_fields_service import SuggestionFieldService

router = APIRouter(prefix="/api/suggestion-fields", tags=["suggestion-fields"])

_repository = SuggestionFieldPostgresRepository()
_service = SuggestionFieldService(repository=_repository)


def get_service() -> SuggestionFieldService:
    return _service


@router.get("", response_model=list[SuggestionFieldResponse])
def list_suggestion_fields(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SuggestionFieldService = Depends(get_service),
):
    return service.list_suggestion_fields()


@router.post(
    "", response_model=SuggestionFieldResponse, status_code=status.HTTP_201_CREATED
)
def create_suggestion_field(
    payload: SuggestionFieldCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionFieldService = Depends(get_service),
):
    return service.create_suggestion_field(payload)


@router.get("/{entity_id}", response_model=SuggestionFieldResponse)
def get_suggestion_field(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SuggestionFieldService = Depends(get_service),
):
    entity = service.get_suggestion_field(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuggestionField '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SuggestionFieldResponse)
def update_suggestion_field(
    entity_id: str,
    payload: SuggestionFieldUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionFieldService = Depends(get_service),
):
    entity = service.update_suggestion_field(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuggestionField '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suggestion_field(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionFieldService = Depends(get_service),
):
    if not service.delete_suggestion_field(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuggestionField '{entity_id}' not found.",
        )
