"""Business logic for sequence_run_steps."""

from app.models.sequence_run_steps import SequenceRunStepCreate, SequenceRunStepUpdate
from app.repositories.sequence_run_steps_postgres_repository import (
    SequenceRunStepPostgresRepository,
)


class SequenceRunStepService:
    """Service layer for sequence_run_steps."""

    def __init__(self, repository: SequenceRunStepPostgresRepository):
        self.repository = repository

    def list_sequence_run_steps(self) -> list[dict]:
        return self.repository.list_all()

    def get_sequence_run_step(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_sequence_run_step(self, payload: SequenceRunStepCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_sequence_run_step(
        self, entity_id: str, payload: SequenceRunStepUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_sequence_run_step(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
