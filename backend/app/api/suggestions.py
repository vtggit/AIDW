"""Suggestion API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.dashboard.service import accept_suggestion, dismiss_suggestion
from app.models.dashboard_items import DashboardItemResponse
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
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionService = Depends(get_service),
):
    return service.create_suggestion(payload, actor=user.username or user.sub)


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
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionService = Depends(get_service),
):
    entity = service.update_suggestion(
        entity_id, payload, actor=user.username or user.sub
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suggestion(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SuggestionService = Depends(get_service),
):
    if not service.delete_suggestion(entity_id, actor=user.username or user.sub):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion '{entity_id}' not found.",
        )


@router.post("/{entity_id}/accept", response_model=DashboardItemResponse)
def accept(
    entity_id: str,
    dashboard_id: str | None = None,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Accept a suggestion into a dashboard item (idempotent). Optional ``dashboard_id`` query param
    targets a specific dashboard; omitted, a default dashboard is used."""
    try:
        return accept_suggestion(entity_id, dashboard_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{entity_id}/dismiss", response_model=SuggestionResponse)
def dismiss(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Dismiss a suggestion (sticky — the reconciler never resurrects it)."""
    try:
        return dismiss_suggestion(entity_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
