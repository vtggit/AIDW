"""RetentionRun data models."""

from pydantic import BaseModel, Field


class RetentionRunCreate(BaseModel):
    """Request model for creating a retention_run."""

    name: str = Field(..., min_length=1)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)


class RetentionRunUpdate(BaseModel):
    """Request model for updating a retention_run (all fields optional)."""

    name: str | None = Field(default=None)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)


class RetentionRunResponse(BaseModel):
    """Response model for a retention_run record."""

    id: str
    name: str
    status: str | None = None
    trigger: str | None = None
    created_at: str
    updated_at: str
