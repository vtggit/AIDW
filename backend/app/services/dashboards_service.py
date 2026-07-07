"""Business logic for dashboards."""

from app.models.dashboards import DashboardCreate, DashboardUpdate
from app.repositories.dashboards_postgres_repository import DashboardPostgresRepository


class DashboardService:
    """Service layer for dashboards."""

    def __init__(self, repository: DashboardPostgresRepository):
        self.repository = repository

    def list_dashboards(self) -> list[dict]:
        return self.repository.list_all()

    def get_dashboard(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_dashboard(self, payload: DashboardCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_dashboard(self, entity_id: str, payload: DashboardUpdate) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_dashboard(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
