"""Business logic for deletion_requests."""

from app.models.deletion_requests import DeletionRequestCreate, DeletionRequestUpdate
from app.repositories.deletion_requests_postgres_repository import (
    DeletionRequestPostgresRepository,
)


class DeletionRequestService:
    """Service layer for deletion_requests."""

    def __init__(self, repository: DeletionRequestPostgresRepository):
        self.repository = repository

    def list_deletion_requests(self) -> list[dict]:
        return self.repository.list_all()

    def get_deletion_request(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_deletion_request(self, payload: DeletionRequestCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_deletion_request(
        self, entity_id: str, payload: DeletionRequestUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_deletion_request(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
