"""Business logic for sequence_runs."""

from app.models.sequence_runs import SequenceRunCreate, SequenceRunUpdate
from app.repositories.sequence_runs_postgres_repository import (
    SequenceRunPostgresRepository,
)


class SequenceRunService:
    """Service layer for sequence_runs."""

    def __init__(self, repository: SequenceRunPostgresRepository):
        self.repository = repository

    def list_sequence_runs(self) -> list[dict]:
        return self.repository.list_all()

    def get_sequence_run(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_sequence_run(self, payload: SequenceRunCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_sequence_run(
        self, entity_id: str, payload: SequenceRunUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_sequence_run(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
