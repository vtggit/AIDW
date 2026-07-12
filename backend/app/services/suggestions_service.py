"""Business logic for suggestions."""

from app.models.suggestions import SuggestionCreate, SuggestionUpdate
from app.repositories.suggestions_postgres_repository import (
    SuggestionPostgresRepository,
)


class SuggestionService:
    """Service layer for suggestions."""

    def __init__(self, repository: SuggestionPostgresRepository):
        self.repository = repository

    def list_suggestions(self) -> list[dict]:
        return self.repository.list_all()

    def get_suggestion(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_suggestion(
        self, payload: SuggestionCreate, actor: str | None = None
    ) -> dict:
        return self.repository.create(payload.model_dump(), actor=actor)

    def update_suggestion(
        self, entity_id: str, payload: SuggestionUpdate, actor: str | None = None
    ) -> dict | None:
        return self.repository.update(
            entity_id, payload.model_dump(exclude_unset=True), actor=actor
        )

    def delete_suggestion(self, entity_id: str, actor: str | None = None) -> bool:
        return self.repository.delete(entity_id, actor=actor)
