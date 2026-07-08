"""Run API routes (the ingestion run spine)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.runs import RunCreate, RunResponse, RunUpdate
from app.repositories.runs_postgres_repository import RunPostgresRepository
from app.services.runs_service import RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])

_repository = RunPostgresRepository()
_service = RunService(repository=_repository)


def get_service() -> RunService:
    return _service


@router.get("", response_model=list[RunResponse])
def list_runs(
    _user: AuthUser = Depends(require_authenticated_user),
    service: RunService = Depends(get_service),
):
    return service.list_runs()


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RunService = Depends(get_service),
):
    return service.create_run(payload)


@router.get("/{entity_id}", response_model=RunResponse)
def get_run(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: RunService = Depends(get_service),
):
    entity = service.get_run(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=RunResponse)
def update_run(
    entity_id: str,
    payload: RunUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RunService = Depends(get_service),
):
    entity = service.update_run(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: RunService = Depends(get_service),
):
    if not service.delete_run(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{entity_id}' not found.",
        )
