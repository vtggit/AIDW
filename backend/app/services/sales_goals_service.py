"""Service layer for sales goals and quota tracking."""

from app.models.sales_goals import SalesGoalCreate, SalesGoalUpdate
from app.repositories.sales_goals_postgres_repository import (
    SalesGoalsPostgresRepository,
)


class SalesGoalsService:
    """Business logic for sales goals."""

    def __init__(self, repository: SalesGoalsPostgresRepository):
        self._repo = repository

    def list_goals(self, active_only: bool = False) -> list[dict]:
        goals = self._repo.list_all(active_only=active_only)
        for goal in goals:
            goal["progress_percent"] = self._calc_progress(goal)
        return goals

    def get_goal(self, goal_id: str) -> dict | None:
        goal = self._repo.get_by_id(goal_id)
        if goal:
            goal["progress_percent"] = self._calc_progress(goal)
        return goal

    def create_goal(self, payload: SalesGoalCreate, actor=None) -> dict:
        data = payload.model_dump()
        return self._repo.create(data)

    def update_goal(self, goal_id: str, payload: SalesGoalUpdate) -> dict | None:
        data = payload.model_dump(exclude_unset=True)
        return self._repo.update(goal_id, data)

    def update_current_value(self, goal_id: str, value: float) -> dict | None:
        return self._repo.update_current_value(goal_id, value)

    def delete_goal(self, goal_id: str) -> bool:
        return self._repo.delete(goal_id)

    def get_progress(self) -> dict:
        result = self._repo.get_progress()
        for goal in result["goals"]:
            goal["progress_percent"] = self._calc_progress(goal)
        return result

    def recalculate_all_current_values(self) -> list[dict]:
        """Recalculate current values from actual data (leads, contacts, etc.)."""
        goals = self._repo.list_all()
        updated = []
        for goal in goals:
            value = self._compute_current_value(goal)
            result = self._repo.update_current_value(goal["id"], value)
            if result:
                result["progress_percent"] = self._calc_progress(result)
                updated.append(result)
        return updated

    def _calc_progress(self, goal: dict) -> float:
        if goal.get("target_value", 0) <= 0:
            return 0.0
        return round((goal["current_value"] / goal["target_value"]) * 100, 1)

    def _compute_current_value(self, goal: dict) -> float:
        """Compute current value from actual CRM data based on goal type."""
        from app.repositories.sales_goals_postgres_repository import get_cursor

        goal_type = goal.get("type")
        if goal_type == "revenue":
            with get_cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(value), 0) FROM leads WHERE stage = 'Won'"
                )
                return float(cur.fetchone()[0])
        elif goal_type == "deals":
            with get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM leads WHERE stage = 'Won'")
                return float(cur.fetchone()[0])
        elif goal_type == "contacts":
            with get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM contacts")
                return float(cur.fetchone()[0])
        elif goal_type == "activities":
            with get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM activities")
                return float(cur.fetchone()[0])
        return goal.get("current_value", 0.0)
