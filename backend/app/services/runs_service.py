"""Business logic for runs."""

from app.models.runs import RunCreate, RunUpdate
from app.repositories.runs_postgres_repository import RunPostgresRepository


class RunService:
    """Service layer for runs."""

    def __init__(self, repository: RunPostgresRepository):
        self.repository = repository

    def list_runs(self) -> list[dict]:
        return self.repository.list_all()

    def get_run(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_run(self, payload: RunCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_run(self, entity_id: str, payload: RunUpdate) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_run(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
