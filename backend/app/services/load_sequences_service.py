"""Business logic for load_sequences."""

from app.models.load_sequences import LoadSequenceCreate, LoadSequenceUpdate
from app.repositories.load_sequences_postgres_repository import (
    LoadSequencePostgresRepository,
)


class LoadSequenceService:
    """Service layer for load_sequences."""

    def __init__(self, repository: LoadSequencePostgresRepository):
        self.repository = repository

    def list_load_sequences(self) -> list[dict]:
        return self.repository.list_all()

    def get_load_sequence(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_load_sequence(self, payload: LoadSequenceCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_load_sequence(
        self, entity_id: str, payload: LoadSequenceUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_load_sequence(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
