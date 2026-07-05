"""Business logic for deal outcomes (win/loss reason tracking)."""

from app.auth.models import AuthUser
from app.models.deal_outcomes import DealOutcomeCreate, DealOutcomeUpdate
from app.repositories.deal_outcomes_postgres_repository import (
    DealOutcomesPostgresRepository,
)


class DealOutcomesService:
    """Service layer for deal outcomes."""

    def __init__(self, repository: DealOutcomesPostgresRepository):
        self.repository = repository

    def create_outcome(self, payload: DealOutcomeCreate, actor: AuthUser) -> dict:
        """Create a win/loss outcome for a lead."""
        data = payload.model_dump()
        return self.repository.create(data)

    def get_outcome(self, outcome_id: str) -> dict | None:
        return self.repository.get_by_id(outcome_id)

    def get_outcome_for_lead(self, lead_id: str) -> dict | None:
        return self.repository.get_by_lead_id(lead_id)

    def list_outcomes(self) -> list[dict]:
        return self.repository.list_all()

    def update_outcome(
        self, outcome_id: str, payload: DealOutcomeUpdate
    ) -> dict | None:
        data = payload.model_dump(exclude_unset=True)
        return self.repository.update(outcome_id, data)

    def delete_outcome(self, outcome_id: str) -> bool:
        return self.repository.delete(outcome_id)

    def get_analytics(self) -> dict:
        return self.repository.get_analytics()
