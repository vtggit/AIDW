"""Pipeline API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.pipelines import (
    PipelineCreate,
    PipelineResponse,
    PipelineUpdate,
)
from app.repositories.pipelines_postgres_repository import (
    PipelinePostgresRepository,
)
from app.services.pipelines_service import PipelineService

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])

_repository = PipelinePostgresRepository()
_service = PipelineService(repository=_repository)


def get_service() -> PipelineService:
    return _service


@router.get("", response_model=list[PipelineResponse])
def list_pipelines(
    _user: AuthUser = Depends(require_authenticated_user),
    service: PipelineService = Depends(get_service),
):
    return service.list_pipelines()


@router.post("", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
def create_pipeline(
    payload: PipelineCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: PipelineService = Depends(get_service),
):
    return service.create_pipeline(payload)


@router.get("/{entity_id}", response_model=PipelineResponse)
def get_pipeline(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: PipelineService = Depends(get_service),
):
    entity = service.get_pipeline(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=PipelineResponse)
def update_pipeline(
    entity_id: str,
    payload: PipelineUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: PipelineService = Depends(get_service),
):
    entity = service.update_pipeline(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: PipelineService = Depends(get_service),
):
    if not service.delete_pipeline(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{entity_id}' not found.",
        )
