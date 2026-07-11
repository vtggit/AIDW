"""AuditLog data models."""

from pydantic import BaseModel, Field


class AuditLogCreate(BaseModel):
    """Request model for creating a audit_log."""

    name: str = Field(..., min_length=1)
    actor: str | None = Field(default=None)
    entity_type: str | None = Field(default=None)
    entity_id: str | None = Field(default=None)
    detail: str | None = Field(default=None)
    action: str | None = Field(default=None)


class AuditLogUpdate(BaseModel):
    """Request model for updating a audit_log (all fields optional)."""

    name: str | None = Field(default=None)
    actor: str | None = Field(default=None)
    entity_type: str | None = Field(default=None)
    entity_id: str | None = Field(default=None)
    detail: str | None = Field(default=None)
    action: str | None = Field(default=None)


class AuditLogResponse(BaseModel):
    """Response model for a audit_log record."""

    id: str
    name: str
    actor: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    detail: str | None = None
    action: str | None = None
    created_at: str
    updated_at: str
