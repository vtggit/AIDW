"""DiscoveryRun API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.discovery_runs import (
    DiscoveryRunCreate,
    DiscoveryRunResponse,
    DiscoveryRunUpdate,
)
from app.repositories.discovery_runs_postgres_repository import (
    DiscoveryRunPostgresRepository,
)
from app.services.discovery_runs_service import DiscoveryRunService

router = APIRouter(prefix="/api/discovery-runs", tags=["discovery-runs"])

_repository = DiscoveryRunPostgresRepository()
_service = DiscoveryRunService(repository=_repository)


def get_service() -> DiscoveryRunService:
    return _service


@router.get("", response_model=list[DiscoveryRunResponse])
def list_discovery_runs(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DiscoveryRunService = Depends(get_service),
):
    return service.list_discovery_runs()


@router.post(
    "", response_model=DiscoveryRunResponse, status_code=status.HTTP_201_CREATED
)
def create_discovery_run(
    payload: DiscoveryRunCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DiscoveryRunService = Depends(get_service),
):
    return service.create_discovery_run(payload)


@router.get("/{entity_id}", response_model=DiscoveryRunResponse)
def get_discovery_run(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DiscoveryRunService = Depends(get_service),
):
    entity = service.get_discovery_run(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DiscoveryRun '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DiscoveryRunResponse)
def update_discovery_run(
    entity_id: str,
    payload: DiscoveryRunUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DiscoveryRunService = Depends(get_service),
):
    entity = service.update_discovery_run(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DiscoveryRun '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discovery_run(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DiscoveryRunService = Depends(get_service),
):
    if not service.delete_discovery_run(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DiscoveryRun '{entity_id}' not found.",
        )
