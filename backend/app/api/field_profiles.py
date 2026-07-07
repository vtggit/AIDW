"""FieldProfile API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.field_profiles import (
    FieldProfileCreate,
    FieldProfileResponse,
    FieldProfileUpdate,
)
from app.repositories.field_profiles_postgres_repository import (
    FieldProfilePostgresRepository,
)
from app.services.field_profiles_service import FieldProfileService

router = APIRouter(prefix="/api/field-profiles", tags=["field-profiles"])

_repository = FieldProfilePostgresRepository()
_service = FieldProfileService(repository=_repository)


def get_service() -> FieldProfileService:
    return _service


@router.get("", response_model=list[FieldProfileResponse])
def list_field_profiles(
    _user: AuthUser = Depends(require_authenticated_user),
    service: FieldProfileService = Depends(get_service),
):
    return service.list_field_profiles()


@router.post(
    "", response_model=FieldProfileResponse, status_code=status.HTTP_201_CREATED
)
def create_field_profile(
    payload: FieldProfileCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FieldProfileService = Depends(get_service),
):
    return service.create_field_profile(payload)


@router.get("/{entity_id}", response_model=FieldProfileResponse)
def get_field_profile(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: FieldProfileService = Depends(get_service),
):
    entity = service.get_field_profile(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FieldProfile '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=FieldProfileResponse)
def update_field_profile(
    entity_id: str,
    payload: FieldProfileUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FieldProfileService = Depends(get_service),
):
    entity = service.update_field_profile(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FieldProfile '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field_profile(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FieldProfileService = Depends(get_service),
):
    if not service.delete_field_profile(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FieldProfile '{entity_id}' not found.",
        )
