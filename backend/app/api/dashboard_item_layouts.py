"""DashboardItemLayout API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

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
    caller: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    """List layouts owned by the authenticated caller."""
    return service.list_dashboard_item_layouts(caller.sub)


@router.post(
    "", response_model=DashboardItemLayoutResponse, status_code=status.HTTP_201_CREATED
)
def create_dashboard_item_layout(
    payload: DashboardItemLayoutCreate,
    caller: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    """Create a layout for the authenticated caller.

    user_id is derived from the token subject; it must not be supplied in the
    request body (the Pydantic model rejects it).
    """
    return service.create_dashboard_item_layout(payload, caller.sub)


@router.get("/{entity_id}", response_model=DashboardItemLayoutResponse)
def get_dashboard_item_layout(
    entity_id: str,
    caller: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    """Fetch a layout — only if it belongs to the authenticated caller."""
    entity = service.get_dashboard_item_layout(entity_id, caller.sub)
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
    caller: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    """Update a layout — only if it belongs to the authenticated caller.

    Any user_id in the payload is ignored; ownership comes from the token.
    """
    entity = service.update_dashboard_item_layout(entity_id, payload, caller.sub)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemLayout '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_item_layout(
    entity_id: str,
    caller: AuthUser = Depends(require_authenticated_user),
    service: DashboardItemLayoutService = Depends(get_service),
):
    """Delete a layout — only if it belongs to the authenticated caller."""
    if not service.delete_dashboard_item_layout(entity_id, caller.sub):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DashboardItemLayout '{entity_id}' not found.",
        )
