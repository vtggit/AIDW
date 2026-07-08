"""Business logic for delta_cursors."""

from app.models.delta_cursors import DeltaCursorCreate, DeltaCursorUpdate
from app.repositories.delta_cursors_postgres_repository import (
    DeltaCursorPostgresRepository,
)


class DeltaCursorService:
    """Service layer for delta_cursors."""

    def __init__(self, repository: DeltaCursorPostgresRepository):
        self.repository = repository

    def list_delta_cursors(self) -> list[dict]:
        return self.repository.list_all()

    def get_delta_cursor(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_delta_cursor(self, payload: DeltaCursorCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_delta_cursor(
        self, entity_id: str, payload: DeltaCursorUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_delta_cursor(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
