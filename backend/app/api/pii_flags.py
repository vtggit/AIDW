"""PiiFlag API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.pii_flags import PiiFlagCreate, PiiFlagResponse, PiiFlagUpdate
from app.repositories.pii_flags_postgres_repository import PiiFlagPostgresRepository
from app.services.pii_flags_service import PiiFlagService

router = APIRouter(prefix="/api/pii-flags", tags=["pii-flags"])

_repository = PiiFlagPostgresRepository()
_service = PiiFlagService(repository=_repository)


def get_service() -> PiiFlagService:
    return _service


@router.get("", response_model=list[PiiFlagResponse])
def list_pii_flags(
    _user: AuthUser = Depends(require_authenticated_user),
    service: PiiFlagService = Depends(get_service),
):
    return service.list_pii_flags()


@router.post("", response_model=PiiFlagResponse, status_code=status.HTTP_201_CREATED)
def create_pii_flag(
    payload: PiiFlagCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: PiiFlagService = Depends(get_service),
):
    return service.create_pii_flag(payload)


@router.get("/{entity_id}", response_model=PiiFlagResponse)
def get_pii_flag(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: PiiFlagService = Depends(get_service),
):
    entity = service.get_pii_flag(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PiiFlag '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=PiiFlagResponse)
def update_pii_flag(
    entity_id: str,
    payload: PiiFlagUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: PiiFlagService = Depends(get_service),
):
    entity = service.update_pii_flag(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PiiFlag '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pii_flag(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: PiiFlagService = Depends(get_service),
):
    if not service.delete_pii_flag(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PiiFlag '{entity_id}' not found.",
        )
