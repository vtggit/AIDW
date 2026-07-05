"""Sales goals and quota tracking API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.sales_goals import (
    SalesGoalCreate,
    SalesGoalProgress,
    SalesGoalResponse,
    SalesGoalUpdate,
)
from app.repositories.sales_goals_postgres_repository import (
    SalesGoalsPostgresRepository,
)
from app.services.sales_goals_service import SalesGoalsService

router = APIRouter(prefix="/api/sales-goals", tags=["sales-goals"])

_repository = SalesGoalsPostgresRepository()
_service = SalesGoalsService(repository=_repository)


def get_service() -> SalesGoalsService:
    return _service


@router.get("", response_model=list[SalesGoalResponse])
def list_goals(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    active_only: bool = False,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SalesGoalsService = Depends(get_service),
):
    """List all sales goals. Requires authentication."""
    rows = service.list_goals(active_only=active_only)
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post("", response_model=SalesGoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: SalesGoalCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SalesGoalsService = Depends(get_service),
):
    """Create a new sales goal. Requires admin role."""
    return service.create_goal(payload, actor=_user)


@router.get("/progress", response_model=SalesGoalProgress)
def get_progress(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SalesGoalsService = Depends(get_service),
):
    """Get progress summary for all active goals. Requires authentication."""
    return service.get_progress()


@router.post("/recalculate", response_model=list[SalesGoalResponse])
def recalculate_values(
    _user: AuthUser = Depends(require_authenticated_user),
    service: SalesGoalsService = Depends(get_service),
):
    """Recalculate current values from CRM data. Requires authentication."""
    return service.recalculate_all_current_values()


@router.get("/{goal_id}", response_model=SalesGoalResponse)
def get_goal(
    goal_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: SalesGoalsService = Depends(get_service),
):
    """Get a single sales goal by ID. Requires authentication."""
    goal = service.get_goal(goal_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sales goal '{goal_id}' not found.",
        )
    return goal


@router.patch("/{goal_id}", response_model=SalesGoalResponse)
def update_goal(
    goal_id: str,
    payload: SalesGoalUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SalesGoalsService = Depends(get_service),
):
    """Update a sales goal. Requires admin role."""
    goal = service.update_goal(goal_id, payload)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sales goal '{goal_id}' not found.",
        )
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: SalesGoalsService = Depends(get_service),
):
    """Delete a sales goal. Requires admin role."""
    deleted = service.delete_goal(goal_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sales goal '{goal_id}' not found.",
        )
