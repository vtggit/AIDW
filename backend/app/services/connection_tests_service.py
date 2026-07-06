"""Business logic for connection_tests."""

from app.models.connection_tests import ConnectionTestCreate, ConnectionTestUpdate
from app.repositories.connection_tests_postgres_repository import (
    ConnectionTestPostgresRepository,
)


class ConnectionTestService:
    """Service layer for connection_tests."""

    def __init__(self, repository: ConnectionTestPostgresRepository):
        self.repository = repository

    def list_connection_tests(self) -> list[dict]:
        return self.repository.list_all()

    def get_connection_test(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_connection_test(self, payload: ConnectionTestCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_connection_test(
        self, entity_id: str, payload: ConnectionTestUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_connection_test(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
