"""Business logic for source_connections."""

from app.models.source_connections import SourceConnectionCreate, SourceConnectionUpdate
from app.repositories.source_connections_postgres_repository import (
    SourceConnectionPostgresRepository,
)


class SourceConnectionService:
    """Service layer for source_connections."""

    def __init__(self, repository: SourceConnectionPostgresRepository):
        self.repository = repository

    def list_source_connections(self) -> list[dict]:
        return self.repository.list_all()

    def get_source_connection(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_source_connection(self, payload: SourceConnectionCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_source_connection(
        self, entity_id: str, payload: SourceConnectionUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_source_connection(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
