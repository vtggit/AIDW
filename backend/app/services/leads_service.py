"""Leads service - business logic layer."""

from app.auth.models import AuthUser
from app.models.audit import AuditEvent
from app.models.leads import ALLOWED_STAGES, LeadCreate, LeadUpdate
from app.repositories.leads_postgres_repository import LeadsPostgresRepository
from app.services.audit_service import AuditService

# Fields that must always be present in a backend-returned lead record.
_AUTHORITATIVE_FIELDS = (
    "id",
    "name",
    "company",
    "email",
    "phone",
    "value",
    "stage",
    "source",
    "notes",
    "company_id",
    "created_at",
    "updated_at",
)


class LeadsService:
    """Handles Leads business logic and validation."""

    def __init__(
        self,
        repository: LeadsPostgresRepository,
        audit_service: AuditService,
    ):
        self.repository = repository
        self.audit_service = audit_service

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def list_leads(self, company_id: str | None = None) -> list[dict]:
        rows = self.repository.list_all(company_id=company_id)
        return [_ensure_authoritative_shape(r) for r in rows]

    def get_lead(self, lead_id: str) -> dict | None:
        row = self.repository.get_by_id(lead_id)
        if row is None:
            return None
        return _ensure_authoritative_shape(row)

    def create_lead(self, payload: LeadCreate, actor: AuthUser) -> dict:
        _validate_lead_name(payload.name)
        _validate_stage(payload.stage)
        _normalize_fields(payload)
        data = payload.model_dump(exclude_unset=True)
        lead = _ensure_authoritative_shape(self.repository.create(data))

        self.audit_service.write(
            AuditEvent(
                entity_type="lead",
                entity_id=lead["id"],
                action="created",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "name": lead["name"],
                    "email": lead.get("email"),
                    "company": lead.get("company"),
                    "stage": lead.get("stage"),
                },
            )
        )

        return lead

    def update_lead(
        self,
        lead_id: str,
        payload: LeadUpdate,
        actor: AuthUser,
    ) -> dict | None:
        existing = self.repository.get_by_id(lead_id)
        if not existing:
            return None

        if payload.name is not None:
            _validate_lead_name(payload.name)
        if payload.stage is not None:
            _validate_stage(payload.stage)

        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        result = self.repository.update(lead_id, data)
        if result is None:
            return None

        lead = _ensure_authoritative_shape(result)

        changed_fields = [
            k
            for k in data
            if k
            in (
                "name",
                "company",
                "email",
                "phone",
                "value",
                "stage",
                "source",
                "notes",
            )
        ]

        self.audit_service.write(
            AuditEvent(
                entity_type="lead",
                entity_id=lead_id,
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

        return lead

    def delete_lead(self, lead_id: str, actor: AuthUser) -> bool:
        existing = self.repository.get_by_id(lead_id)
        deleted = self.repository.delete(lead_id)
        if not deleted:
            return False

        self.audit_service.write(
            AuditEvent(
                entity_type="lead",
                entity_id=lead_id,
                action="deleted",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "name": existing.get("name") if existing else None,
                    "email": existing.get("email") if existing else None,
                    "stage": existing.get("stage") if existing else None,
                },
            )
        )

        return True


# --------------------------------------------------------------------- #
#  Validation helpers                                                     #
# --------------------------------------------------------------------- #


def _validate_lead_name(name: str) -> None:
    """Name must be a non-empty string after trimming."""
    if not name or not name.strip():
        raise ValueError("Lead name is required.")


def _validate_stage(stage: str) -> None:
    """Stage must be one of the allowed values."""
    if stage not in ALLOWED_STAGES:
        raise ValueError(
            f"Invalid stage '{stage}'. Allowed values: {', '.join(sorted(ALLOWED_STAGES))}"
        )


def _normalize_fields(payload: LeadCreate | LeadUpdate) -> None:
    """Light normalization: trim whitespace on string fields."""
    for field in ("name", "company", "email", "phone", "notes"):
        val = getattr(payload, field, None)
        if isinstance(val, str):
            setattr(payload, field, val.strip() or None)


# --------------------------------------------------------------------- #
#  Response-shape guarantee                                              #
# --------------------------------------------------------------------- #


def _ensure_authoritative_shape(record: dict) -> dict:
    """
    Guarantee every returned lead dict contains the authoritative set
    of fields, even if the repository layer ever drops one.
    """
    return {k: record.get(k) for k in _AUTHORITATIVE_FIELDS}
