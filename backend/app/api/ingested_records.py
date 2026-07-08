"""IngestedRecord API routes (the CDC op-log)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.ingested_records import (
    IngestedRecordCreate,
    IngestedRecordResponse,
    IngestedRecordUpdate,
)
from app.repositories.ingested_records_postgres_repository import (
    IngestedRecordPostgresRepository,
)
from app.services.ingested_records_service import IngestedRecordService

router = APIRouter(prefix="/api/ingested-records", tags=["ingested-records"])

_repository = IngestedRecordPostgresRepository()
_service = IngestedRecordService(repository=_repository)


def get_service() -> IngestedRecordService:
    return _service


@router.get("", response_model=list[IngestedRecordResponse])
def list_ingested_records(
    _user: AuthUser = Depends(require_authenticated_user),
    service: IngestedRecordService = Depends(get_service),
):
    return service.list_ingested_records()


@router.post(
    "", response_model=IngestedRecordResponse, status_code=status.HTTP_201_CREATED
)
def create_ingested_record(
    payload: IngestedRecordCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: IngestedRecordService = Depends(get_service),
):
    return service.create_ingested_record(payload)


@router.get("/{entity_id}", response_model=IngestedRecordResponse)
def get_ingested_record(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: IngestedRecordService = Depends(get_service),
):
    entity = service.get_ingested_record(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IngestedRecord '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=IngestedRecordResponse)
def update_ingested_record(
    entity_id: str,
    payload: IngestedRecordUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: IngestedRecordService = Depends(get_service),
):
    entity = service.update_ingested_record(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IngestedRecord '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ingested_record(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: IngestedRecordService = Depends(get_service),
):
    if not service.delete_ingested_record(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IngestedRecord '{entity_id}' not found.",
        )
