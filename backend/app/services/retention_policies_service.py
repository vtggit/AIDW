"""Business logic for retention_policies."""

from app.models.retention_policies import RetentionPolicyCreate, RetentionPolicyUpdate
from app.repositories.retention_policies_postgres_repository import (
    RetentionPolicyPostgresRepository,
)


class RetentionPolicyService:
    """Service layer for retention_policies."""

    def __init__(self, repository: RetentionPolicyPostgresRepository):
        self.repository = repository

    def list_retention_policies(self) -> list[dict]:
        return self.repository.list_all()

    def get_retention_policy(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_retention_policy(self, payload: RetentionPolicyCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_retention_policy(
        self, entity_id: str, payload: RetentionPolicyUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_retention_policy(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
