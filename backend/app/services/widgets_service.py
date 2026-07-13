"""Business logic for widgets."""

from app.models.widgets import WidgetCreate, WidgetUpdate
from app.repositories.widgets_postgres_repository import WidgetPostgresRepository


class WidgetService:
    """Service layer for widgets."""

    def __init__(self, repository: WidgetPostgresRepository):
        self.repository = repository

    def list_widgets(self) -> list[dict]:
        return self.repository.list_all()

    def get_widget(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_widget(self, payload: WidgetCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_widget(self, entity_id: str, payload: WidgetUpdate) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_widget(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
