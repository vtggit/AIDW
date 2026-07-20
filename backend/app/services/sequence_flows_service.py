"""Business logic for sequence_flows."""

from app.models.sequence_flows import SequenceFlowCreate, SequenceFlowUpdate
from app.repositories.sequence_flows_postgres_repository import (
    SequenceFlowPostgresRepository,
)


class SequenceFlowService:
    """Service layer for sequence_flows."""

    def __init__(self, repository: SequenceFlowPostgresRepository):
        self.repository = repository

    def list_sequence_flows(self) -> list[dict]:
        return self.repository.list_all()

    def get_sequence_flow(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_sequence_flow(self, payload: SequenceFlowCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_sequence_flow(
        self, entity_id: str, payload: SequenceFlowUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_sequence_flow(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
