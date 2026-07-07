"""DashboardItemField API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.dashboard_item_fields import (
    DashboardItemFieldCreate,
    DashboardItemFieldResponse,
    DashboardItemFieldUpdate,
)
from app.repositories.dashboard_item_fields_postgres_repository import (
    DashboardItemFieldPostgresRepository,
)
from app.services.dashboard_item_fields_service import DashboardItemFieldService

router = APIRouter(prefix="/api/dashboard-item-fields", tags=["dashboard-item-fields"])

_repository = DashboardItemFieldPostgresRepository()
_service = DashboardItemFieldService(repository=_repository)


def get_service() -> DashboardItemFieldService:
    return _service


@router.get("", response_model=list[DashboardItemFieldResponse])
def list_dashboard_item_fields(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemFieldService = Depends(get_service),
):
    return service.list_dashboard_item_fields()


@router.post(
    "", response_model=DashboardItemFieldResponse, status_code=status.HTTP_201_CREATED
)
def create_dashboard_item_field(
    payload: DashboardItemFieldCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemFieldService = Depends(get_service),
):
    return service.create_dashboard_item_field(payload)


@router.get("/{entity_id}", response_model=DashboardItemFieldResponse)
def get_dashboard_item_field(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemFieldService = Depends(get_service),
):
    entity = service.get_dashboard_item_field(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemField '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DashboardItemFieldResponse)
def update_dashboard_item_field(
    entity_id: str,
    payload: DashboardItemFieldUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemFieldService = Depends(get_service),
):
    entity = service.update_dashboard_item_field(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemField '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_item_field(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardItemFieldService = Depends(get_service),
):
    if not service.delete_dashboard_item_field(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemField '{entity_id}' not found.",
        )
