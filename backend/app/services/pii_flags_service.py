"""Business logic for pii_flags."""

from app.models.pii_flags import PiiFlagCreate, PiiFlagUpdate
from app.repositories.pii_flags_postgres_repository import PiiFlagPostgresRepository


class PiiFlagService:
    """Service layer for pii_flags."""

    def __init__(self, repository: PiiFlagPostgresRepository):
        self.repository = repository

    def list_pii_flags(self) -> list[dict]:
        return self.repository.list_all()

    def get_pii_flag(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_pii_flag(self, payload: PiiFlagCreate, actor: str | None = None) -> dict:
        return self.repository.create(payload.model_dump(), actor=actor)

    def update_pii_flag(
        self, entity_id: str, payload: PiiFlagUpdate, actor: str | None = None
    ) -> dict | None:
        return self.repository.update(
            entity_id, payload.model_dump(exclude_unset=True), actor=actor
        )

    def delete_pii_flag(self, entity_id: str, actor: str | None = None) -> bool:
        return self.repository.delete(entity_id, actor=actor)
