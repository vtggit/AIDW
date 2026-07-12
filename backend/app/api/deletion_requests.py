"""DeletionRequest API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.deletion_requests import (
    DeletionRequestCreate,
    DeletionRequestResponse,
    DeletionRequestUpdate,
)
from app.repositories.deletion_requests_postgres_repository import (
    DeletionRequestPostgresRepository,
)
from app.services.deletion_requests_service import DeletionRequestService

router = APIRouter(prefix="/api/deletion-requests", tags=["deletion-requests"])

_repository = DeletionRequestPostgresRepository()
_service = DeletionRequestService(repository=_repository)


def get_service() -> DeletionRequestService:
    return _service


@router.get("", response_model=list[DeletionRequestResponse])
def list_deletion_requests(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DeletionRequestService = Depends(get_service),
):
    return service.list_deletion_requests()


@router.post(
    "", response_model=DeletionRequestResponse, status_code=status.HTTP_201_CREATED
)
def create_deletion_request(
    payload: DeletionRequestCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    return service.create_deletion_request(payload)


@router.get("/{entity_id}", response_model=DeletionRequestResponse)
def get_deletion_request(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DeletionRequestService = Depends(get_service),
):
    entity = service.get_deletion_request(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DeletionRequestResponse)
def update_deletion_request(
    entity_id: str,
    payload: DeletionRequestUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    entity = service.update_deletion_request(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deletion_request(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DeletionRequestService = Depends(get_service),
):
    if not service.delete_deletion_request(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DeletionRequest '{entity_id}' not found.",
        )
