"""Business logic for sequence_steps."""

from app.models.sequence_steps import SequenceStepCreate, SequenceStepUpdate
from app.repositories.sequence_steps_postgres_repository import (
    SequenceStepPostgresRepository,
)


class SequenceStepService:
    """Service layer for sequence_steps."""

    def __init__(self, repository: SequenceStepPostgresRepository):
        self.repository = repository

    def list_sequence_steps(self) -> list[dict]:
        return self.repository.list_all()

    def get_sequence_step(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_sequence_step(self, payload: SequenceStepCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_sequence_step(
        self, entity_id: str, payload: SequenceStepUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_sequence_step(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
