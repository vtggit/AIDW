"""ProcessStep API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.process_steps import (
    ProcessStepCreate,
    ProcessStepResponse,
    ProcessStepUpdate,
)
from app.repositories.process_steps_postgres_repository import (
    ProcessStepPostgresRepository,
)
from app.services.process_steps_service import ProcessStepService

router = APIRouter(prefix="/api/process-steps", tags=["process-steps"])

_repository = ProcessStepPostgresRepository()
_service = ProcessStepService(repository=_repository)


def get_service() -> ProcessStepService:
    return _service


@router.get("", response_model=list[ProcessStepResponse])
def list_process_steps(
    _user: AuthUser = Depends(require_authenticated_user),
    service: ProcessStepService = Depends(get_service),
):
    return service.list_process_steps()


@router.post(
    "", response_model=ProcessStepResponse, status_code=status.HTTP_201_CREATED
)
def create_process_step(
    payload: ProcessStepCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ProcessStepService = Depends(get_service),
):
    return service.create_process_step(payload)


@router.get("/{entity_id}", response_model=ProcessStepResponse)
def get_process_step(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: ProcessStepService = Depends(get_service),
):
    entity = service.get_process_step(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProcessStep '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=ProcessStepResponse)
def update_process_step(
    entity_id: str,
    payload: ProcessStepUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ProcessStepService = Depends(get_service),
):
    entity = service.update_process_step(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProcessStep '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_process_step(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ProcessStepService = Depends(get_service),
):
    if not service.delete_process_step(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProcessStep '{entity_id}' not found.",
        )
