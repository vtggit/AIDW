"""Source API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.sources import SourceCreate, SourceResponse, SourceUpdate
from app.repositories.sources_postgres_repository import SourcePostgresRepository
from app.services.sources_service import SourceService

router = APIRouter(prefix="/api/sources", tags=["sources"])

_repository = SourcePostgresRepository()
_service = SourceService(repository=_repository)


def get_service() -> SourceService:
    return _service


@router.get("", response_model=list[SourceResponse])
def list_sources(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SourceService = Depends(get_service),
):
    return service.list_sources()


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceService = Depends(get_service),
):
    return service.create_source(payload)


@router.get("/{entity_id}", response_model=SourceResponse)
def get_source(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SourceService = Depends(get_service),
):
    entity = service.get_source(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SourceResponse)
def update_source(
    entity_id: str,
    payload: SourceUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceService = Depends(get_service),
):
    entity = service.update_source(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceService = Depends(get_service),
):
    if not service.delete_source(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{entity_id}' not found.",
        )
