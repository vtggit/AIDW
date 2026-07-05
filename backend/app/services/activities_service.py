"""Activities service - business logic layer."""

from app.auth.models import AuthUser
from app.models.activities import (
    ALLOWED_STATUSES,
    ALLOWED_TYPES,
    ActivityCreate,
    ActivityUpdate,
)
from app.models.audit import AuditEvent
from app.repositories.activities_postgres_repository import ActivitiesPostgresRepository
from app.services.audit_service import AuditService

# Fields that must always be present in a backend-returned activity record.
_AUTHORITATIVE_FIELDS = (
    "id",
    "type",
    "description",
    "contact_name",
    "occurred_at",
    "due_date",
    "status",
    "created_at",
    "updated_at",
)


class ActivitiesService:
    """Handles Activities business logic and validation."""

    def __init__(
        self,
        repository: ActivitiesPostgresRepository,
        audit_service: AuditService,
    ):
        self.repository = repository
        self.audit_service = audit_service

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def list_activities(self) -> list[dict]:
        rows = self.repository.list_all()
        return [_ensure_authoritative_shape(r) for r in rows]

    def get_activity(self, activity_id: str) -> dict | None:
        row = self.repository.get_by_id(activity_id)
        if row is None:
            return None
        return _ensure_authoritative_shape(row)

    def create_activity(self, payload: ActivityCreate, actor: AuthUser) -> dict:
        _validate_activity_type(payload.type)
        _validate_activity_status(payload.status)
        _normalize_fields(payload)
        data = payload.model_dump(exclude_unset=True)
        activity = _ensure_authoritative_shape(self.repository.create(data))

        self.audit_service.write(
            AuditEvent(
                entity_type="activity",
                entity_id=activity["id"],
                action="created",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "type": activity["type"],
                    "description": activity["description"],
                    "status": activity["status"],
                },
            )
        )

        return activity

    def update_activity(
        self,
        activity_id: str,
        payload: ActivityUpdate,
        actor: AuthUser,
    ) -> dict | None:
        existing = self.repository.get_by_id(activity_id)
        if not existing:
            return None

        if payload.type is not None:
            _validate_activity_type(payload.type)
        if payload.status is not None:
            _validate_activity_status(payload.status)

        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        result = self.repository.update(activity_id, data)
        if result is None:
            return None

        activity = _ensure_authoritative_shape(result)

        changed_fields = [
            k
            for k in data
            if k
            in (
                "type",
                "description",
                "contact_name",
                "occurred_at",
                "due_date",
                "status",
            )
        ]

        self.audit_service.write(
            AuditEvent(
                entity_type="activity",
                entity_id=activity_id,
                action="updated",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "changed_fields": changed_fields,
                },
            )
        )

        return activity

    def delete_activity(self, activity_id: str, actor: AuthUser) -> bool:
        existing = self.repository.get_by_id(activity_id)
        deleted = self.repository.delete(activity_id)
        if not deleted:
            return False

        self.audit_service.write(
            AuditEvent(
                entity_type="activity",
                entity_id=activity_id,
                action="deleted",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "type": existing.get("type") if existing else None,
                    "description": existing.get("description") if existing else None,
                },
            )
        )

        return True


# --------------------------------------------------------------------- #
#  Validation helpers                                                     #
# --------------------------------------------------------------------- #


def _validate_activity_type(activity_type: str) -> None:
    """Activity type must be one of the allowed values."""
    if activity_type not in ALLOWED_TYPES:
        raise ValueError(
            f"Invalid activity type '{activity_type}'. "
            f"Allowed values: {', '.join(sorted(ALLOWED_TYPES))}"
        )


def _validate_activity_status(status: str) -> None:
    """Status must be one of the allowed values."""
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. "
            f"Allowed values: {', '.join(sorted(ALLOWED_STATUSES))}"
        )


def _normalize_fields(payload: ActivityCreate | ActivityUpdate) -> None:
    """Light normalization: trim whitespace on string fields."""
    for field in ("description", "contact_name"):
        val = getattr(payload, field, None)
        if isinstance(val, str):
            setattr(payload, field, val.strip() or None)


# --------------------------------------------------------------------- #
#  Response-shape guarantee                                              #
# --------------------------------------------------------------------- #


def _ensure_authoritative_shape(record: dict) -> dict:
    """
    Guarantee every returned activity dict contains the authoritative set
    of fields, even if the repository layer ever drops one.
    """
    return {k: record.get(k) for k in _AUTHORITATIVE_FIELDS}
