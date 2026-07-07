"""Business logic for suggestion_fields."""

from app.models.suggestion_fields import SuggestionFieldCreate, SuggestionFieldUpdate
from app.repositories.suggestion_fields_postgres_repository import (
    SuggestionFieldPostgresRepository,
)


class SuggestionFieldService:
    """Service layer for suggestion_fields."""

    def __init__(self, repository: SuggestionFieldPostgresRepository):
        self.repository = repository

    def list_suggestion_fields(self) -> list[dict]:
        return self.repository.list_all()

    def get_suggestion_field(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_suggestion_field(self, payload: SuggestionFieldCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_suggestion_field(
        self, entity_id: str, payload: SuggestionFieldUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_suggestion_field(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
