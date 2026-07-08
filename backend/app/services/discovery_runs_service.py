"""Business logic for discovery_runs."""

from app.models.discovery_runs import DiscoveryRunCreate, DiscoveryRunUpdate
from app.repositories.discovery_runs_postgres_repository import (
    DiscoveryRunPostgresRepository,
)


class DiscoveryRunService:
    """Service layer for discovery_runs."""

    def __init__(self, repository: DiscoveryRunPostgresRepository):
        self.repository = repository

    def list_discovery_runs(self) -> list[dict]:
        return self.repository.list_all()

    def get_discovery_run(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_discovery_run(self, payload: DiscoveryRunCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_discovery_run(
        self, entity_id: str, payload: DiscoveryRunUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_discovery_run(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
