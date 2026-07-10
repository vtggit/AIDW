"""RetentionRun API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.retention_runs import (
    RetentionRunCreate,
    RetentionRunResponse,
    RetentionRunUpdate,
)
from app.repositories.retention_runs_postgres_repository import (
    RetentionRunPostgresRepository,
)
from app.services.retention_runs_service import RetentionRunService

router = APIRouter(prefix="/api/retention-runs", tags=["retention-runs"])

_repository = RetentionRunPostgresRepository()
_service = RetentionRunService(repository=_repository)


def get_service() -> RetentionRunService:
    return _service


@router.get("", response_model=list[RetentionRunResponse])
def list_retention_runs(
    _user: AuthUser = Depends(require_authenticated_user),
    service: RetentionRunService = Depends(get_service),
):
    return service.list_retention_runs()


@router.post(
    "", response_model=RetentionRunResponse, status_code=status.HTTP_201_CREATED
)
def create_retention_run(
    payload: RetentionRunCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RetentionRunService = Depends(get_service),
):
    return service.create_retention_run(payload)


@router.get("/{entity_id}", response_model=RetentionRunResponse)
def get_retention_run(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: RetentionRunService = Depends(get_service),
):
    entity = service.get_retention_run(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RetentionRun '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=RetentionRunResponse)
def update_retention_run(
    entity_id: str,
    payload: RetentionRunUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RetentionRunService = Depends(get_service),
):
    entity = service.update_retention_run(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RetentionRun '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_retention_run(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RetentionRunService = Depends(get_service),
):
    if not service.delete_retention_run(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RetentionRun '{entity_id}' not found.",
        )
