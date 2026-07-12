"""Business logic for suppression_entries."""

from app.models.suppression_entries import (
    SuppressionEntryCreate,
    SuppressionEntryUpdate,
)
from app.repositories.suppression_entries_postgres_repository import (
    SuppressionEntryPostgresRepository,
)


class SuppressionEntryService:
    """Service layer for suppression_entries."""

    def __init__(self, repository: SuppressionEntryPostgresRepository):
        self.repository = repository

    def list_suppression_entries(self) -> list[dict]:
        return self.repository.list_all()

    def get_suppression_entry(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_suppression_entry(self, payload: SuppressionEntryCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_suppression_entry(
        self, entity_id: str, payload: SuppressionEntryUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_suppression_entry(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
