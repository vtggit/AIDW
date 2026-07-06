"""Business logic for odata_service_configs."""

from app.models.odata_service_configs import (
    OdataServiceConfigCreate,
    OdataServiceConfigUpdate,
)
from app.repositories.odata_service_configs_postgres_repository import (
    OdataServiceConfigPostgresRepository,
)


class OdataServiceConfigService:
    """Service layer for odata_service_configs."""

    def __init__(self, repository: OdataServiceConfigPostgresRepository):
        self.repository = repository

    def list_odata_service_configs(self) -> list[dict]:
        return self.repository.list_all()

    def get_odata_service_config(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_odata_service_config(self, payload: OdataServiceConfigCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_odata_service_config(
        self, entity_id: str, payload: OdataServiceConfigUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_odata_service_config(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
