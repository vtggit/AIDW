"""Audit event data models."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Internal audit event to be written to the repository."""

    entity_type: str
    entity_id: str
    action: str
    actor_sub: str
    actor_username: str | None = None
    actor_email: str | None = None
    actor_roles: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)


class AuditEventResponse(BaseModel):
    """Audit event returned by the API."""

    id: int
    entity_type: str
    entity_id: str
    action: str
    actor_sub: str
    actor_username: str | None = None
    actor_email: str | None = None
    actor_roles: str | None = None
    timestamp: str
    details: dict[str, Any] = Field(default_factory=dict)
