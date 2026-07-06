"""ConnectionTest API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.connection_tests import (
    ConnectionTestCreate,
    ConnectionTestResponse,
    ConnectionTestUpdate,
)
from app.repositories.connection_tests_postgres_repository import (
    ConnectionTestPostgresRepository,
)
from app.services.connection_tests_service import ConnectionTestService

router = APIRouter(prefix="/api/connection-tests", tags=["connection-tests"])

_repository = ConnectionTestPostgresRepository()
_service = ConnectionTestService(repository=_repository)


def get_service() -> ConnectionTestService:
    return _service


@router.get("", response_model=list[ConnectionTestResponse])
def list_connection_tests(
    _user: AuthUser = Depends(require_authenticated_user),
    service: ConnectionTestService = Depends(get_service),
):
    return service.list_connection_tests()


@router.post(
    "", response_model=ConnectionTestResponse, status_code=status.HTTP_201_CREATED
)
def create_connection_test(
    payload: ConnectionTestCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ConnectionTestService = Depends(get_service),
):
    return service.create_connection_test(payload)


@router.get("/{entity_id}", response_model=ConnectionTestResponse)
def get_connection_test(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: ConnectionTestService = Depends(get_service),
):
    entity = service.get_connection_test(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=ConnectionTestResponse)
def update_connection_test(
    entity_id: str,
    payload: ConnectionTestUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ConnectionTestService = Depends(get_service),
):
    entity = service.update_connection_test(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection_test(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ConnectionTestService = Depends(get_service),
):
    if not service.delete_connection_test(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
