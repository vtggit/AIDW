"""DashboardItem API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.dashboard_items import (
    DashboardItemCreate,
    DashboardItemResponse,
    DashboardItemUpdate,
)
from app.repositories.dashboard_items_postgres_repository import (
    DashboardItemPostgresRepository,
)
from app.services.dashboard_items_service import DashboardItemService

router = APIRouter(prefix="/api/dashboard-items", tags=["dashboard-items"])

_repository = DashboardItemPostgresRepository()
_service = DashboardItemService(repository=_repository)


def get_service() -> DashboardItemService:
    return _service


@router.get("", response_model=list[DashboardItemResponse])
def list_dashboard_items(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemService = Depends(get_service),
):
    return service.list_dashboard_items()


@router.post(
    "", response_model=DashboardItemResponse, status_code=status.HTTP_201_CREATED
)
def create_dashboard_item(
    payload: DashboardItemCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemService = Depends(get_service),
):
    return service.create_dashboard_item(payload)


@router.get("/{entity_id}", response_model=DashboardItemResponse)
def get_dashboard_item(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemService = Depends(get_service),
):
    entity = service.get_dashboard_item(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItem '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DashboardItemResponse)
def update_dashboard_item(
    entity_id: str,
    payload: DashboardItemUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemService = Depends(get_service),
):
    entity = service.update_dashboard_item(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItem '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_item(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemService = Depends(get_service),
):
    if not service.delete_dashboard_item(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItem '{entity_id}' not found.",
        )
