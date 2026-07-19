"""Business logic for process_definitions."""

from app.models.process_definitions import (
    ProcessDefinitionCreate,
    ProcessDefinitionUpdate,
)
from app.repositories.process_definitions_postgres_repository import (
    ProcessDefinitionPostgresRepository,
)


class ProcessDefinitionService:
    """Service layer for process_definitions."""

    def __init__(self, repository: ProcessDefinitionPostgresRepository):
        self.repository = repository

    def list_process_definitions(self) -> list[dict]:
        return self.repository.list_all()

    def get_process_definition(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_process_definition(self, payload: ProcessDefinitionCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_process_definition(
        self, entity_id: str, payload: ProcessDefinitionUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_process_definition(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
