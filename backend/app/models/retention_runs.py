"""RetentionRun data models."""

from pydantic import BaseModel, Field


class RetentionRunCreate(BaseModel):
    """Request model for creating a retention_run."""

    records_anonymized: int | None = Field(default=None)

    records_purged: int | None = Field(default=None)

    policy_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)


class RetentionRunUpdate(BaseModel):
    """Request model for updating a retention_run (all fields optional)."""

    records_anonymized: int | None = Field(default=None)

    records_purged: int | None = Field(default=None)

    policy_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)


class RetentionRunResponse(BaseModel):
    """Response model for a retention_run record."""

    records_anonymized: int | None = None

    records_purged: int | None = None

    policy_id: str | None = None

    id: str
    name: str
    status: str | None = None
    trigger: str | None = None
    created_at: str
    updated_at: str
