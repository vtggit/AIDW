"""DashboardItemLayout API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.dashboard_item_layouts import (
    DashboardItemLayoutCreate,
    DashboardItemLayoutResponse,
    DashboardItemLayoutUpdate,
)
from app.repositories.dashboard_item_layouts_postgres_repository import (
    DashboardItemLayoutPostgresRepository,
)
from app.services.dashboard_item_layouts_service import DashboardItemLayoutService

router = APIRouter(
    prefix="/api/dashboard-item-layouts", tags=["dashboard-item-layouts"]
)

_repository = DashboardItemLayoutPostgresRepository()
_service = DashboardItemLayoutService(repository=_repository)


def get_service() -> DashboardItemLayoutService:
    return _service


@router.get("", response_model=list[DashboardItemLayoutResponse])
def list_dashboard_item_layouts(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    return service.list_dashboard_item_layouts()


@router.post(
    "", response_model=DashboardItemLayoutResponse, status_code=status.HTTP_201_CREATED
)
def create_dashboard_item_layout(
    payload: DashboardItemLayoutCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemLayoutService = Depends(get_service),
):
    return service.create_dashboard_item_layout(payload)


@router.get("/{entity_id}", response_model=DashboardItemLayoutResponse)
def get_dashboard_item_layout(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    entity = service.get_dashboard_item_layout(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemLayout '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DashboardItemLayoutResponse)
def update_dashboard_item_layout(
    entity_id: str,
    payload: DashboardItemLayoutUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemLayoutService = Depends(get_service),
):
    entity = service.update_dashboard_item_layout(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemLayout '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_item_layout(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemLayoutService = Depends(get_service),
):
    if not service.delete_dashboard_item_layout(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemLayout '{entity_id}' not found.",
        )
