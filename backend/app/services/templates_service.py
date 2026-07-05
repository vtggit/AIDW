"""Templates service - business logic layer."""

from app.auth.models import AuthUser
from app.models.audit import AuditEvent
from app.models.templates import ALLOWED_CATEGORIES, TemplateCreate, TemplateUpdate
from app.repositories.templates_postgres_repository import TemplatesPostgresRepository
from app.services.audit_service import AuditService

# Fields that must always be present in a backend-returned template record.
_AUTHORITATIVE_FIELDS = (
    "id",
    "name",
    "category",
    "subject",
    "content",
    "created_at",
    "updated_at",
)


class TemplatesService:
    """Handles Templates business logic and validation."""

    def __init__(
        self,
        repository: TemplatesPostgresRepository,
        audit_service: AuditService,
    ):
        self.repository = repository
        self.audit_service = audit_service

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def list_templates(self) -> list[dict]:
        rows = self.repository.list_all()
        return [_ensure_authoritative_shape(r) for r in rows]

    def get_template(self, template_id: str) -> dict | None:
        row = self.repository.get_by_id(template_id)
        if row is None:
            return None
        return _ensure_authoritative_shape(row)

    def create_template(self, payload: TemplateCreate, actor: AuthUser) -> dict:
        _validate_template_name(payload.name)
        _validate_category(payload.category)
        _normalize_fields(payload)
        data = payload.model_dump(exclude_unset=True)
        template = _ensure_authoritative_shape(self.repository.create(data))

        self.audit_service.write(
            AuditEvent(
                entity_type="template",
                entity_id=template["id"],
                action="created",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "name": template["name"],
                    "category": template.get("category"),
                },
            )
        )

        return template

    def update_template(
        self,
        template_id: str,
        payload: TemplateUpdate,
        actor: AuthUser,
    ) -> dict | None:
        existing = self.repository.get_by_id(template_id)
        if not existing:
            return None

        if payload.name is not None:
            _validate_template_name(payload.name)
        if payload.category is not None:
            _validate_category(payload.category)

        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        result = self.repository.update(template_id, data)
        if result is None:
            return None

        template = _ensure_authoritative_shape(result)

        changed_fields = [
            k for k in data if k in ("name", "category", "subject", "content")
        ]

        self.audit_service.write(
            AuditEvent(
                entity_type="template",
                entity_id=template_id,
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

        return template

    def delete_template(self, template_id: str, actor: AuthUser) -> bool:
        existing = self.repository.get_by_id(template_id)
        deleted = self.repository.delete(template_id)
        if not deleted:
            return False

        self.audit_service.write(
            AuditEvent(
                entity_type="template",
                entity_id=template_id,
                action="deleted",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "name": existing.get("name") if existing else None,
                    "category": existing.get("category") if existing else None,
                },
            )
        )

        return True


# --------------------------------------------------------------------- #
#  Validation helpers                                                     #
# --------------------------------------------------------------------- #


def _validate_template_name(name: str) -> None:
    """Name must be a non-empty string after trimming."""
    if not name or not name.strip():
        raise ValueError("Template name is required.")


def _validate_category(category: str) -> None:
    """Category must be one of the allowed values."""
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Allowed values: {', '.join(sorted(ALLOWED_CATEGORIES))}"
        )


def _normalize_fields(payload: TemplateCreate | TemplateUpdate) -> None:
    """Light normalization: trim whitespace on string fields."""
    for field in ("name", "subject"):
        val = getattr(payload, field, None)
        if isinstance(val, str):
            setattr(payload, field, val.strip() or None)


# --------------------------------------------------------------------- #
#  Response-shape guarantee                                              #
# --------------------------------------------------------------------- #


def _ensure_authoritative_shape(record: dict) -> dict:
    """
    Guarantee every returned template dict contains the authoritative set
    of fields, even if the repository layer ever drops one.
    """
    return {k: record.get(k) for k in _AUTHORITATIVE_FIELDS}
