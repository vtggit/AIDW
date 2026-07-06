"""OdataServiceConfig API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.odata_service_configs import (
    OdataServiceConfigCreate,
    OdataServiceConfigResponse,
    OdataServiceConfigUpdate,
)
from app.repositories.odata_service_configs_postgres_repository import (
    OdataServiceConfigPostgresRepository,
)
from app.services.odata_service_configs_service import OdataServiceConfigService

router = APIRouter(prefix="/api/odata-service-configs", tags=["odata-service-configs"])

_repository = OdataServiceConfigPostgresRepository()
_service = OdataServiceConfigService(repository=_repository)


def get_service() -> OdataServiceConfigService:
    return _service


@router.get("", response_model=list[OdataServiceConfigResponse])
def list_odata_service_configs(
    _user: AuthUser = Depends(require_authenticated_user),
    service: OdataServiceConfigService = Depends(get_service),
):
    return service.list_odata_service_configs()


@router.post(
    "", response_model=OdataServiceConfigResponse, status_code=status.HTTP_201_CREATED
)
def create_odata_service_config(
    payload: OdataServiceConfigCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: OdataServiceConfigService = Depends(get_service),
):
    return service.create_odata_service_config(payload)


@router.get("/{entity_id}", response_model=OdataServiceConfigResponse)
def get_odata_service_config(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: OdataServiceConfigService = Depends(get_service),
):
    entity = service.get_odata_service_config(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OdataServiceConfig '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=OdataServiceConfigResponse)
def update_odata_service_config(
    entity_id: str,
    payload: OdataServiceConfigUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: OdataServiceConfigService = Depends(get_service),
):
    entity = service.update_odata_service_config(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OdataServiceConfig '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_odata_service_config(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: OdataServiceConfigService = Depends(get_service),
):
    if not service.delete_odata_service_config(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OdataServiceConfig '{entity_id}' not found.",
        )
