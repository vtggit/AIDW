"""Business logic for source_credentials."""

from app.models.source_credentials import SourceCredentialCreate, SourceCredentialUpdate
from app.repositories.source_credentials_postgres_repository import (
    SourceCredentialPostgresRepository,
)


class SourceCredentialService:
    """Service layer for source_credentials."""

    def __init__(self, repository: SourceCredentialPostgresRepository):
        self.repository = repository

    def list_source_credentials(self) -> list[dict]:
        return self.repository.list_all()

    def get_source_credential(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_source_credential(
        self, payload: SourceCredentialCreate, actor: str | None = None
    ) -> dict:
        return self.repository.create(payload.model_dump(), actor=actor)

    def update_source_credential(
        self, entity_id: str, payload: SourceCredentialUpdate, actor: str | None = None
    ) -> dict | None:
        return self.repository.update(
            entity_id, payload.model_dump(exclude_unset=True), actor=actor
        )

    def delete_source_credential(
        self, entity_id: str, actor: str | None = None
    ) -> bool:
        return self.repository.delete(entity_id, actor=actor)
