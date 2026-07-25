"""Business logic for dashboard_item_layouts."""

from app.models.dashboard_item_layouts import (
    DashboardItemLayoutCreate,
    DashboardItemLayoutUpdate,
)
from app.repositories.dashboard_item_layouts_postgres_repository import (
    DashboardItemLayoutPostgresRepository,
)


class DashboardItemLayoutService:
    """Service layer for dashboard_item_layouts.

    Every operation is scoped to the authenticated caller's user_id (taken from
    their token subject).  The service never trusts a user_id supplied in a
    request payload — it always uses the ``caller_user_sub`` argument instead.
    """

    def __init__(self, repository: DashboardItemLayoutPostgresRepository):
        self.repository = repository

    def list_dashboard_item_layouts(self, caller_user_sub: str) -> list[dict]:
        return self.repository.list_by_user(caller_user_sub)

    def get_dashboard_item_layout(
        self, entity_id: str, caller_user_sub: str
    ) -> dict | None:
        return self.repository.get_by_id_and_owner(entity_id, caller_user_sub)

    def create_dashboard_item_layout(
        self, payload: DashboardItemLayoutCreate, caller_user_sub: str
    ) -> dict:
        data = payload.model_dump()
        # Defensive: ensure no user_id leaks from the model (it should not exist).
        data.pop("user_id", None)
        return self.repository.create_for_user(data, caller_user_sub)

    def update_dashboard_item_layout(
        self, entity_id: str, payload: DashboardItemLayoutUpdate, caller_user_sub: str
    ) -> dict | None:
        data = payload.model_dump(exclude_unset=True)
        # Strip any user_id from the payload — ownership is enforced via token.
        data.pop("user_id", None)
        return self.repository.update_for_owner(entity_id, data, caller_user_sub)

    def delete_dashboard_item_layout(
        self, entity_id: str, caller_user_sub: str
    ) -> bool:
        return self.repository.delete_for_owner(entity_id, caller_user_sub)
