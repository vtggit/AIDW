"""Deal outcomes API routes (win/loss reason tracking)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.deal_outcomes import (
    DealOutcomeAnalytics,
    DealOutcomeCreate,
    DealOutcomeResponse,
    DealOutcomeUpdate,
)
from app.repositories.deal_outcomes_postgres_repository import (
    DealOutcomesPostgresRepository,
)
from app.services.deal_outcomes_service import DealOutcomesService

router = APIRouter(prefix="/api/deal-outcomes", tags=["deal-outcomes"])

_repository = DealOutcomesPostgresRepository()
_service = DealOutcomesService(repository=_repository)


def get_service() -> DealOutcomesService:
    return _service


@router.get("", response_model=list[DealOutcomeResponse])
def list_outcomes(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    _user: AuthUser = Depends(require_authenticated_user),
    service: DealOutcomesService = Depends(get_service),
):
    """List all deal outcomes. Requires authentication."""
    rows = service.list_outcomes()
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post(
    "", response_model=DealOutcomeResponse, status_code=status.HTTP_201_CREATED
)
def create_outcome(
    payload: DealOutcomeCreate,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DealOutcomesService = Depends(get_service),
):
    """Create a win/loss outcome for a lead. Requires authentication."""
    return service.create_outcome(payload, actor=_user)


@router.get("/analytics", response_model=DealOutcomeAnalytics)
def get_analytics(
    _user: AuthUser = Depends(require_authenticated_user),
    service: DealOutcomesService = Depends(get_service),
):
    """Get win/loss analytics summary. Requires authentication."""
    return service.get_analytics()


@router.get("/{outcome_id}", response_model=DealOutcomeResponse)
def get_outcome(
    outcome_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DealOutcomesService = Depends(get_service),
):
    """Get a single deal outcome by ID. Requires authentication."""
    outcome = service.get_outcome(outcome_id)
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deal outcome '{outcome_id}' not found.",
        )
    return outcome


@router.patch("/{outcome_id}", response_model=DealOutcomeResponse)
def update_outcome(
    outcome_id: str,
    payload: DealOutcomeUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DealOutcomesService = Depends(get_service),
):
    """Update a deal outcome. Requires admin role."""
    outcome = service.update_outcome(outcome_id, payload)
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deal outcome '{outcome_id}' not found.",
        )
    return outcome


@router.delete("/{outcome_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outcome(
    outcome_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: DealOutcomesService = Depends(get_service),
):
    """Delete a deal outcome. Requires admin role."""
    deleted = service.delete_outcome(outcome_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deal outcome '{outcome_id}' not found.",
        )


@router.get("/leads/{lead_id}", response_model=DealOutcomeResponse | None)
def get_outcome_for_lead(
    lead_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: DealOutcomesService = Depends(get_service),
):
    """Get the deal outcome for a specific lead. Requires authentication."""
    return service.get_outcome_for_lead(lead_id)
