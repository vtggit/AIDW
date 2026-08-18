"""Business logic for feed_credentials."""

from app.models.feed_credentials import FeedCredentialCreate, FeedCredentialUpdate
from app.repositories.feed_credentials_postgres_repository import (
    FeedCredentialPostgresRepository,
)


class FeedCredentialService:
    """Service layer for feed_credentials."""

    def __init__(self, repository: FeedCredentialPostgresRepository):
        self.repository = repository

    def list_feed_credentials(self) -> list[dict]:
        return self.repository.list_all()

    def get_feed_credential(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_feed_credential(self, payload: FeedCredentialCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_feed_credential(
        self, entity_id: str, payload: FeedCredentialUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_feed_credential(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
