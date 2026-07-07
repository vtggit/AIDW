"""Business logic for dashboard_item_fields."""

from app.models.dashboard_item_fields import (
    DashboardItemFieldCreate,
    DashboardItemFieldUpdate,
)
from app.repositories.dashboard_item_fields_postgres_repository import (
    DashboardItemFieldPostgresRepository,
)


class DashboardItemFieldService:
    """Service layer for dashboard_item_fields."""

    def __init__(self, repository: DashboardItemFieldPostgresRepository):
        self.repository = repository

    def list_dashboard_item_fields(self) -> list[dict]:
        return self.repository.list_all()

    def get_dashboard_item_field(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_dashboard_item_field(self, payload: DashboardItemFieldCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_dashboard_item_field(
        self, entity_id: str, payload: DashboardItemFieldUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_dashboard_item_field(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
