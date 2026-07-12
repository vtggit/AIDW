"""SourceConnection API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.source_connections import (
    SourceConnectionCreate,
    SourceConnectionResponse,
    SourceConnectionUpdate,
)
from app.repositories.source_connections_postgres_repository import (
    SourceConnectionPostgresRepository,
)
from app.services.source_connections_service import SourceConnectionService

router = APIRouter(prefix="/api/source-connections", tags=["source-connections"])

_repository = SourceConnectionPostgresRepository()
_service = SourceConnectionService(repository=_repository)


def get_service() -> SourceConnectionService:
    return _service


@router.get("", response_model=list[SourceConnectionResponse])
def list_source_connections(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SourceConnectionService = Depends(get_service),
):
    return service.list_source_connections()


@router.post(
    "", response_model=SourceConnectionResponse, status_code=status.HTTP_201_CREATED
)
def create_source_connection(
    payload: SourceConnectionCreate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceConnectionService = Depends(get_service),
):
    return service.create_source_connection(payload, actor=user.username or user.sub)


@router.get("/{entity_id}", response_model=SourceConnectionResponse)
def get_source_connection(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SourceConnectionService = Depends(get_service),
):
    entity = service.get_source_connection(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceConnection '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SourceConnectionResponse)
def update_source_connection(
    entity_id: str,
    payload: SourceConnectionUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceConnectionService = Depends(get_service),
):
    entity = service.update_source_connection(
        entity_id, payload, actor=user.username or user.sub
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceConnection '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source_connection(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceConnectionService = Depends(get_service),
):
    if not service.delete_source_connection(entity_id, actor=user.username or user.sub):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceConnection '{entity_id}' not found.",
        )
