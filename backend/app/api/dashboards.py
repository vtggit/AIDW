"""Dashboard API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.dashboards import DashboardCreate, DashboardResponse, DashboardUpdate
from app.repositories.dashboards_postgres_repository import DashboardPostgresRepository
from app.services.dashboards_service import DashboardService

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

_repository = DashboardPostgresRepository()
_service = DashboardService(repository=_repository)


def get_service() -> DashboardService:
    return _service


@router.get("", response_model=list[DashboardResponse])
def list_dashboards(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardService = Depends(get_service),
):
    return service.list_dashboards()


@router.post("", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
def create_dashboard(
    payload: DashboardCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardService = Depends(get_service),
):
    return service.create_dashboard(payload)


@router.get("/{entity_id}", response_model=DashboardResponse)
def get_dashboard(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DashboardService = Depends(get_service),
):
    entity = service.get_dashboard(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DashboardResponse)
def update_dashboard(
    entity_id: str,
    payload: DashboardUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardService = Depends(get_service),
):
    entity = service.update_dashboard(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DashboardService = Depends(get_service),
):
    if not service.delete_dashboard(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{entity_id}' not found.",
        )
