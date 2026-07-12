"""RetentionPolicy API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.retention_policies import (
    RetentionPolicyCreate,
    RetentionPolicyResponse,
    RetentionPolicyUpdate,
)
from app.repositories.retention_policies_postgres_repository import (
    RetentionPolicyPostgresRepository,
)
from app.services.retention_policies_service import RetentionPolicyService

router = APIRouter(prefix="/api/retention-policies", tags=["retention-policies"])

_repository = RetentionPolicyPostgresRepository()
_service = RetentionPolicyService(repository=_repository)


def get_service() -> RetentionPolicyService:
    return _service


@router.get("", response_model=list[RetentionPolicyResponse])
def list_retention_policies(
    _user: AuthUser = Depends(require_authenticated_user),
    service: RetentionPolicyService = Depends(get_service),
):
    return service.list_retention_policies()


@router.post(
    "", response_model=RetentionPolicyResponse, status_code=status.HTTP_201_CREATED
)
def create_retention_policy(
    payload: RetentionPolicyCreate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RetentionPolicyService = Depends(get_service),
):
    # governance objects are audited (governance #79): actor = the authenticated principal
    return service.create_retention_policy(payload, actor=user.username or user.sub)


@router.get("/{entity_id}", response_model=RetentionPolicyResponse)
def get_retention_policy(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: RetentionPolicyService = Depends(get_service),
):
    entity = service.get_retention_policy(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RetentionPolicy '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=RetentionPolicyResponse)
def update_retention_policy(
    entity_id: str,
    payload: RetentionPolicyUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RetentionPolicyService = Depends(get_service),
):
    entity = service.update_retention_policy(
        entity_id, payload, actor=user.username or user.sub
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RetentionPolicy '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_retention_policy(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RetentionPolicyService = Depends(get_service),
):
    if not service.delete_retention_policy(entity_id, actor=user.username or user.sub):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RetentionPolicy '{entity_id}' not found.",
        )
