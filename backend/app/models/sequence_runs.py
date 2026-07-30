"""SequenceRun data models."""

from pydantic import BaseModel, Field


class SequenceRunCreate(BaseModel):
    """Request model for creating a sequence_run."""

    name: str = Field(..., min_length=1)
    sequence_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)


class SequenceRunUpdate(BaseModel):
    """Request model for updating a sequence_run (all fields optional)."""

    name: str | None = Field(default=None)
    sequence_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)


class SequenceRunResponse(BaseModel):
    """Response model for a sequence_run record."""

    id: str
    name: str
    sequence_id: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str
    updated_at: str
