"""SourceCredential API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.source_credentials import (
    SourceCredentialCreate,
    SourceCredentialResponse,
    SourceCredentialUpdate,
)
from app.repositories.source_credentials_postgres_repository import (
    SourceCredentialPostgresRepository,
)
from app.services.source_credentials_service import SourceCredentialService

router = APIRouter(prefix="/api/source-credentials", tags=["source-credentials"])

_repository = SourceCredentialPostgresRepository()
_service = SourceCredentialService(repository=_repository)


def get_service() -> SourceCredentialService:
    return _service


@router.get("", response_model=list[SourceCredentialResponse])
def list_source_credentials(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SourceCredentialService = Depends(get_service),
):
    return service.list_source_credentials()


@router.post(
    "", response_model=SourceCredentialResponse, status_code=status.HTTP_201_CREATED
)
def create_source_credential(
    payload: SourceCredentialCreate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceCredentialService = Depends(get_service),
):
    return service.create_source_credential(payload, actor=user.username or user.sub)


@router.get("/{entity_id}", response_model=SourceCredentialResponse)
def get_source_credential(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SourceCredentialService = Depends(get_service),
):
    entity = service.get_source_credential(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceCredential '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SourceCredentialResponse)
def update_source_credential(
    entity_id: str,
    payload: SourceCredentialUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceCredentialService = Depends(get_service),
):
    entity = service.update_source_credential(
        entity_id, payload, actor=user.username or user.sub
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceCredential '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source_credential(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SourceCredentialService = Depends(get_service),
):
    if not service.delete_source_credential(entity_id, actor=user.username or user.sub):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceCredential '{entity_id}' not found.",
        )
