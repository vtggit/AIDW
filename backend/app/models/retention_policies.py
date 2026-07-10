"""RetentionPolicy data models."""

from pydantic import BaseModel, Field


class RetentionPolicyCreate(BaseModel):
    """Request model for creating a retention_policy."""

    retention_period_days: int | None = Field(default=None)

    dataset_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    table_class: str | None = Field(default=None)
    action: str | None = Field(default=None)
    scope: str | None = Field(default=None)


class RetentionPolicyUpdate(BaseModel):
    """Request model for updating a retention_policy (all fields optional)."""

    retention_period_days: int | None = Field(default=None)

    dataset_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    table_class: str | None = Field(default=None)
    action: str | None = Field(default=None)
    scope: str | None = Field(default=None)


class RetentionPolicyResponse(BaseModel):
    """Response model for a retention_policy record."""

    retention_period_days: int | None = None

    dataset_id: str | None = None

    id: str
    name: str
    table_class: str | None = None
    action: str | None = None
    scope: str | None = None
    created_at: str
    updated_at: str
