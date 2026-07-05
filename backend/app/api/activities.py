"""Activities API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.activities import ActivityCreate, ActivityResponse, ActivityUpdate
from app.repositories.activities_postgres_repository import ActivitiesPostgresRepository
from app.repositories.audit_postgres_repository import AuditPostgresRepository
from app.services.activities_service import ActivitiesService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/activities", tags=["activities"])

_repository = ActivitiesPostgresRepository()
_audit_repository = AuditPostgresRepository()
_audit_service = AuditService(_audit_repository)
_service = ActivitiesService(repository=_repository, audit_service=_audit_service)


def get_service() -> ActivitiesService:
    return _service


# ------------------------------------------------------------------ #
#  Routes                                                               #
# ------------------------------------------------------------------ #


@router.get("", response_model=list[ActivityResponse])
def list_activities(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    _user: AuthUser = Depends(require_authenticated_user),
    service: ActivitiesService = Depends(get_service),
):
    """List all activities. Requires authentication."""
    rows = service.list_activities()
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: ActivityCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ActivitiesService = Depends(get_service),
):
    """Create a new activity. Requires admin role."""
    try:
        return service.create_activity(payload, actor=_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(
    activity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: ActivitiesService = Depends(get_service),
):
    """Get a single activity by ID. Requires authentication."""
    activity = service.get_activity(activity_id)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity '{activity_id}' not found.",
        )
    return activity


@router.put("/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: str,
    payload: ActivityUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ActivitiesService = Depends(get_service),
):
    """Update an activity. Requires admin role."""
    activity = service.update_activity(activity_id, payload, actor=_user)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity '{activity_id}' not found.",
        )
    return activity


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ActivitiesService = Depends(get_service),
):
    """Delete an activity. Requires admin role."""
    deleted = service.delete_activity(activity_id, actor=_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity '{activity_id}' not found.",
        )
