"""Business logic for pipelines."""

from app.models.pipelines import PipelineCreate, PipelineUpdate
from app.repositories.pipelines_postgres_repository import (
    PipelinePostgresRepository,
)


class PipelineService:
    """Service layer for pipelines."""

    def __init__(self, repository: PipelinePostgresRepository):
        self.repository = repository

    def list_pipelines(self) -> list[dict]:
        return self.repository.list_all()

    def get_pipeline(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_pipeline(
        self, payload: PipelineCreate, actor: str | None = None
    ) -> dict:
        return self.repository.create(payload.model_dump(), actor=actor)

    def update_pipeline(
        self, entity_id: str, payload: PipelineUpdate, actor: str | None = None
    ) -> dict | None:
        return self.repository.update(
            entity_id, payload.model_dump(exclude_unset=True), actor=actor
        )

    def delete_pipeline(self, entity_id: str, actor: str | None = None) -> bool:
        return self.repository.delete(entity_id, actor=actor)
