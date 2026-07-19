"""ProcessDefinition API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.process_definitions import (
    ProcessDefinitionCreate,
    ProcessDefinitionResponse,
    ProcessDefinitionUpdate,
)
from app.repositories.process_definitions_postgres_repository import (
    ProcessDefinitionPostgresRepository,
)
from app.services.process_definitions_service import ProcessDefinitionService

router = APIRouter(prefix="/api/process-definitions", tags=["process-definitions"])

_repository = ProcessDefinitionPostgresRepository()
_service = ProcessDefinitionService(repository=_repository)


def get_service() -> ProcessDefinitionService:
    return _service


@router.get("", response_model=list[ProcessDefinitionResponse])
def list_process_definitions(
    _user: AuthUser = Depends(require_authenticated_user),
    service: ProcessDefinitionService = Depends(get_service),
):
    return service.list_process_definitions()


@router.post(
    "", response_model=ProcessDefinitionResponse, status_code=status.HTTP_201_CREATED
)
def create_process_definition(
    payload: ProcessDefinitionCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ProcessDefinitionService = Depends(get_service),
):
    return service.create_process_definition(payload)


@router.get("/{entity_id}", response_model=ProcessDefinitionResponse)
def get_process_definition(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: ProcessDefinitionService = Depends(get_service),
):
    entity = service.get_process_definition(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProcessDefinition '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=ProcessDefinitionResponse)
def update_process_definition(
    entity_id: str,
    payload: ProcessDefinitionUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ProcessDefinitionService = Depends(get_service),
):
    entity = service.update_process_definition(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProcessDefinition '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_process_definition(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ProcessDefinitionService = Depends(get_service),
):
    if not service.delete_process_definition(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ProcessDefinition '{entity_id}' not found.",
        )
