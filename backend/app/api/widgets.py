"""Widget API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.widgets import WidgetCreate, WidgetResponse, WidgetUpdate
from app.repositories.widgets_postgres_repository import WidgetPostgresRepository
from app.services.widgets_service import WidgetService

router = APIRouter(prefix="/api/widgets", tags=["widgets"])

_repository = WidgetPostgresRepository()
_service = WidgetService(repository=_repository)


def get_service() -> WidgetService:
    return _service


@router.get("", response_model=list[WidgetResponse])
def list_widgets(
    _user: AuthUser = Depends(require_authenticated_user),
    service: WidgetService = Depends(get_service),
):
    return service.list_widgets()


@router.post("", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
def create_widget(
    payload: WidgetCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: WidgetService = Depends(get_service),
):
    return service.create_widget(payload)


@router.get("/{entity_id}", response_model=WidgetResponse)
def get_widget(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: WidgetService = Depends(get_service),
):
    entity = service.get_widget(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=WidgetResponse)
def update_widget(
    entity_id: str,
    payload: WidgetUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: WidgetService = Depends(get_service),
):
    entity = service.update_widget(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: WidgetService = Depends(get_service),
):
    if not service.delete_widget(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{entity_id}' not found.",
        )
