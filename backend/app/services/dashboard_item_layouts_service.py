"""Business logic for dashboard_item_layouts."""

from app.models.dashboard_item_layouts import (
    DashboardItemLayoutCreate,
    DashboardItemLayoutUpdate,
)
from app.repositories.dashboard_item_layouts_postgres_repository import (
    DashboardItemLayoutPostgresRepository,
)


class DashboardItemLayoutService:
    """Service layer for dashboard_item_layouts."""

    def __init__(self, repository: DashboardItemLayoutPostgresRepository):
        self.repository = repository

    def list_dashboard_item_layouts(self) -> list[dict]:
        return self.repository.list_all()

    def get_dashboard_item_layout(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_dashboard_item_layout(self, payload: DashboardItemLayoutCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_dashboard_item_layout(
        self, entity_id: str, payload: DashboardItemLayoutUpdate
    ) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_dashboard_item_layout(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
