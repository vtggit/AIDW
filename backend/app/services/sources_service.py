"""Business logic for sources."""

from app.models.sources import SourceCreate, SourceUpdate
from app.repositories.sources_postgres_repository import SourcePostgresRepository


class SourceService:
    """Service layer for sources."""

    def __init__(self, repository: SourcePostgresRepository):
        self.repository = repository

    def list_sources(self) -> list[dict]:
        return self.repository.list_all()

    def get_source(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_source(self, payload: SourceCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_source(self, entity_id: str, payload: SourceUpdate) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_source(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
