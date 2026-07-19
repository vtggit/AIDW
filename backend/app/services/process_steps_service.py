"""Business logic for process_steps."""

from app.models.process_steps import ProcessStepCreate, ProcessStepUpdate
from app.repositories.process_steps_postgres_repository import (
    ProcessStepPostgresRepository,
)


class ProcessStepService:
    """Service layer for process_steps."""

    def __init__(self, repository: ProcessStepPostgresRepository):
        self.repository = repository

    def list_process_steps(self) -> list[dict]:
        return self.repository.list_all()

    def get_process_step(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_process_step(self, payload: ProcessStepCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_process_step(
        self, entity_id: str, payload: ProcessStepUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_process_step(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
