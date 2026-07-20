"""SequenceFlow API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.sequence_flows import (
    SequenceFlowCreate,
    SequenceFlowResponse,
    SequenceFlowUpdate,
)
from app.repositories.sequence_flows_postgres_repository import (
    SequenceFlowPostgresRepository,
)
from app.services.sequence_flows_service import SequenceFlowService

router = APIRouter(prefix="/api/sequence-flows", tags=["sequence-flows"])

_repository = SequenceFlowPostgresRepository()
_service = SequenceFlowService(repository=_repository)


def get_service() -> SequenceFlowService:
    return _service


@router.get("", response_model=list[SequenceFlowResponse])
def list_sequence_flows(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceFlowService = Depends(get_service),
):
    return service.list_sequence_flows()


@router.post(
    "", response_model=SequenceFlowResponse, status_code=status.HTTP_201_CREATED
)
def create_sequence_flow(
    payload: SequenceFlowCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceFlowService = Depends(get_service),
):
    return service.create_sequence_flow(payload)


@router.get("/{entity_id}", response_model=SequenceFlowResponse)
def get_sequence_flow(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SequenceFlowService = Depends(get_service),
):
    entity = service.get_sequence_flow(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceFlow '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=SequenceFlowResponse)
def update_sequence_flow(
    entity_id: str,
    payload: SequenceFlowUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceFlowService = Depends(get_service),
):
    entity = service.update_sequence_flow(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceFlow '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence_flow(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SequenceFlowService = Depends(get_service),
):
    if not service.delete_sequence_flow(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequenceFlow '{entity_id}' not found.",
        )
