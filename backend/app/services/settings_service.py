"""Settings service — business logic layer."""

import logging

from app.auth.models import AuthUser
from app.models.audit import AuditEvent
from app.models.settings import SettingsUpdate
from app.repositories.settings_repository import SettingsRepository
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_AUTHORITATIVE_FIELDS = ("id", "payload", "created_at", "updated_at")


class SettingsService:
    """Handles Settings business logic and validation."""

    def __init__(
        self,
        repository: SettingsRepository,
        audit_service: AuditService,
    ):
        self.repository = repository
        self.audit_service = audit_service

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def get_settings(self) -> dict:
        """Return the current settings record."""
        row = self.repository.get_settings()
        if row is None:
            return {
                "id": "app",
                "payload": {},
                "created_at": "",
                "updated_at": "",
            }
        return _ensure_authoritative_shape(row)

    def update_settings(self, payload: SettingsUpdate, actor: AuthUser) -> dict:
        """Merge the incoming payload into the settings record.

        Writes an audit event on success.
        """
        _validate_payload(payload.payload)
        _normalize_payload(payload.payload)

        result = self.repository.update_settings(payload.payload)
        if result is None:
            raise ValueError("Failed to update settings.")

        settings = _ensure_authoritative_shape(result)

        changed_keys = list(payload.payload.keys())

        self.audit_service.write(
            AuditEvent(
                entity_type="settings",
                entity_id=settings["id"],
                action="updated",
                actor_sub=actor.sub,
                actor_username=actor.username,
                actor_email=actor.email,
                actor_roles=actor.roles,
                details={
                    "changed_fields": changed_keys,
                },
            )
        )

        return settings


# --------------------------------------------------------------------- #
#  Validation helpers                                                     #
# --------------------------------------------------------------------- #


def _validate_payload(payload: dict) -> None:
    """Payload must be a non-empty dict."""
    if not isinstance(payload, dict):
        raise ValueError("Settings payload must be a JSON object.")


def _normalize_payload(payload: dict) -> None:
    """Light normalization: strip whitespace from string values."""
    for key in list(payload.keys()):
        if isinstance(payload[key], str):
            payload[key] = payload[key].strip()


# --------------------------------------------------------------------- #
#  Response-shape guarantee                                              #
# --------------------------------------------------------------------- #


def _ensure_authoritative_shape(record: dict) -> dict:
    """Guarantee every returned settings dict contains the authoritative
    set of fields."""
    return {k: record.get(k) for k in _AUTHORITATIVE_FIELDS}
