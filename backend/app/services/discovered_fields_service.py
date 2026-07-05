"""Business logic for discovered_fields."""

from app.models.discovered_fields import DiscoveredFieldCreate, DiscoveredFieldUpdate
from app.repositories.discovered_fields_postgres_repository import (
    DiscoveredFieldPostgresRepository,
)


class DiscoveredFieldService:
    """Service layer for discovered_fields."""

    def __init__(self, repository: DiscoveredFieldPostgresRepository):
        self.repository = repository

    def list_discovered_fields(self) -> list[dict]:
        return self.repository.list_all()

    def get_discovered_field(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_discovered_field(self, payload: DiscoveredFieldCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_discovered_field(
        self, entity_id: str, payload: DiscoveredFieldUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_discovered_field(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
