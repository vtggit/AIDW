"""RetentionPolicy data models."""

from pydantic import BaseModel, Field


class RetentionPolicyCreate(BaseModel):
    """Request model for creating a retention_policy."""

    name: str = Field(..., min_length=1)
    table_class: str | None = Field(default=None)
    action: str | None = Field(default=None)
    scope: str | None = Field(default=None)


class RetentionPolicyUpdate(BaseModel):
    """Request model for updating a retention_policy (all fields optional)."""

    name: str | None = Field(default=None)
    table_class: str | None = Field(default=None)
    action: str | None = Field(default=None)
    scope: str | None = Field(default=None)


class RetentionPolicyResponse(BaseModel):
    """Response model for a retention_policy record."""

    id: str
    name: str
    table_class: str | None = None
    action: str | None = None
    scope: str | None = None
    created_at: str
    updated_at: str
