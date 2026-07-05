"""DiscoveredField API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.discovered_fields import (
    DiscoveredFieldCreate,
    DiscoveredFieldResponse,
    DiscoveredFieldUpdate,
)
from app.repositories.discovered_fields_postgres_repository import (
    DiscoveredFieldPostgresRepository,
)
from app.services.discovered_fields_service import DiscoveredFieldService

router = APIRouter(prefix="/api/discovered-fields", tags=["discovered-fields"])

_repository = DiscoveredFieldPostgresRepository()
_service = DiscoveredFieldService(repository=_repository)


def get_service() -> DiscoveredFieldService:
    return _service


@router.get("", response_model=list[DiscoveredFieldResponse])
def list_discovered_fields(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DiscoveredFieldService = Depends(get_service),
):
    return service.list_discovered_fields()


@router.post(
    "", response_model=DiscoveredFieldResponse, status_code=status.HTTP_201_CREATED
)
def create_discovered_field(
    payload: DiscoveredFieldCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DiscoveredFieldService = Depends(get_service),
):
    return service.create_discovered_field(payload)


@router.get("/{entity_id}", response_model=DiscoveredFieldResponse)
def get_discovered_field(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DiscoveredFieldService = Depends(get_service),
):
    entity = service.get_discovered_field(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DiscoveredField '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DiscoveredFieldResponse)
def update_discovered_field(
    entity_id: str,
    payload: DiscoveredFieldUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DiscoveredFieldService = Depends(get_service),
):
    entity = service.update_discovered_field(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DiscoveredField '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discovered_field(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DiscoveredFieldService = Depends(get_service),
):
    if not service.delete_discovered_field(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DiscoveredField '{entity_id}' not found.",
        )
