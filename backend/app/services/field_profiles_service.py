"""Business logic for field_profiles."""

from app.models.field_profiles import FieldProfileCreate, FieldProfileUpdate
from app.repositories.field_profiles_postgres_repository import (
    FieldProfilePostgresRepository,
)


class FieldProfileService:
    """Service layer for field_profiles."""

    def __init__(self, repository: FieldProfilePostgresRepository):
        self.repository = repository

    def list_field_profiles(self) -> list[dict]:
        return self.repository.list_all()

    def get_field_profile(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_field_profile(self, payload: FieldProfileCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_field_profile(
        self, entity_id: str, payload: FieldProfileUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_field_profile(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
