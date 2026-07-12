"""Dataset API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.datasets import DatasetCreate, DatasetResponse, DatasetUpdate
from app.repositories.datasets_postgres_repository import DatasetPostgresRepository
from app.services.datasets_service import DatasetService

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

_repository = DatasetPostgresRepository()
_service = DatasetService(repository=_repository)


def get_service() -> DatasetService:
    return _service


@router.get("", response_model=list[DatasetResponse])
def list_datasets(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DatasetService = Depends(get_service),
):
    return service.list_datasets()


@router.post("", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
def create_dataset(
    payload: DatasetCreate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DatasetService = Depends(get_service),
):
    return service.create_dataset(payload, actor=user.username or user.sub)


@router.get("/{entity_id}", response_model=DatasetResponse)
def get_dataset(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DatasetService = Depends(get_service),
):
    entity = service.get_dataset(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=DatasetResponse)
def update_dataset(
    entity_id: str,
    payload: DatasetUpdate,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DatasetService = Depends(get_service),
):
    entity = service.update_dataset(entity_id, payload, actor=user.username or user.sub)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    entity_id: str,
    user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DatasetService = Depends(get_service),
):
    if not service.delete_dataset(entity_id, actor=user.username or user.sub):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{entity_id}' not found.",
        )
