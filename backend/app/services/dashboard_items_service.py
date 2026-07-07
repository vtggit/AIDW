"""Business logic for dashboard_items."""

from app.models.dashboard_items import DashboardItemCreate, DashboardItemUpdate
from app.repositories.dashboard_items_postgres_repository import (
    DashboardItemPostgresRepository,
)


class DashboardItemService:
    """Service layer for dashboard_items."""

    def __init__(self, repository: DashboardItemPostgresRepository):
        self.repository = repository

    def list_dashboard_items(self) -> list[dict]:
        return self.repository.list_all()

    def get_dashboard_item(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_dashboard_item(self, payload: DashboardItemCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_dashboard_item(
        self, entity_id: str, payload: DashboardItemUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_dashboard_item(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
