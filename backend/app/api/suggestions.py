"""Suggestion API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.suggestions import (
    SuggestionCreate,
    SuggestionResponse,
    SuggestionUpdate,
)
from app.repositories.suggestions_postgres_repository import (
    SuggestionPostgresRepository,
)
from app.services.suggestions_service import SuggestionService

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

_repository = SuggestionPostgresRepository()
_service = SuggestionService(repository=_repository)


def get_service() -> SuggestionService:
    return _service


@router.get("", response_model=list[SuggestionResponse])
def list_suggestions(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SuggestionService = Depends(get_service),
):
    return service.list_suggestions()


@router.post("", response_model=SuggestionResponse, status_code=status.HTTP_201_CREATED)
def create_suggestion(
    payload: SuggestionCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionService = Depends(get_service),
):
    return service.create_suggestion(payload)


@router.get("/{entity_id}", response_model=SuggestionResponse)
def get_suggestion(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SuggestionService = Depends(get_service),
):
    entity = service.get_suggestion(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SuggestionResponse)
def update_suggestion(
    entity_id: str,
    payload: SuggestionUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionService = Depends(get_service),
):
    entity = service.update_suggestion(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suggestion(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionService = Depends(get_service),
):
    if not service.delete_suggestion(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion '{entity_id}' not found.",
        )
