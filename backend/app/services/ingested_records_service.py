"""Business logic for ingested_records."""

from app.models.ingested_records import IngestedRecordCreate, IngestedRecordUpdate
from app.repositories.ingested_records_postgres_repository import (
    IngestedRecordPostgresRepository,
)


class IngestedRecordService:
    """Service layer for ingested_records."""

    def __init__(self, repository: IngestedRecordPostgresRepository):
        self.repository = repository

    def list_ingested_records(self) -> list[dict]:
        return self.repository.list_all()

    def get_ingested_record(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_ingested_record(self, payload: IngestedRecordCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_ingested_record(
        self, entity_id: str, payload: IngestedRecordUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_ingested_record(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
