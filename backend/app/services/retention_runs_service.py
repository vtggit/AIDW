"""Business logic for retention_runs."""

from app.models.retention_runs import RetentionRunCreate, RetentionRunUpdate
from app.repositories.retention_runs_postgres_repository import (
    RetentionRunPostgresRepository,
)


class RetentionRunService:
    """Service layer for retention_runs."""

    def __init__(self, repository: RetentionRunPostgresRepository):
        self.repository = repository

    def list_retention_runs(self) -> list[dict]:
        return self.repository.list_all()

    def get_retention_run(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_retention_run(self, payload: RetentionRunCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_retention_run(
        self, entity_id: str, payload: RetentionRunUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_retention_run(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
