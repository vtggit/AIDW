"""Business logic for datasets."""

from app.models.datasets import DatasetCreate, DatasetUpdate
from app.repositories.datasets_postgres_repository import DatasetPostgresRepository


class DatasetService:
    """Service layer for datasets."""

    def __init__(self, repository: DatasetPostgresRepository):
        self.repository = repository

    def list_datasets(self) -> list[dict]:
        return self.repository.list_all()

    def get_dataset(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_dataset(self, payload: DatasetCreate, actor: str | None = None) -> dict:
        return self.repository.create(payload.model_dump(), actor=actor)

    def update_dataset(
        self, entity_id: str, payload: DatasetUpdate, actor: str | None = None
    ) -> dict | None:
        return self.repository.update(
            entity_id, payload.model_dump(exclude_unset=True), actor=actor
        )

    def delete_dataset(self, entity_id: str, actor: str | None = None) -> bool:
        return self.repository.delete(entity_id, actor=actor)
