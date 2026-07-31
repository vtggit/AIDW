"""SequenceRunStep data models."""

from pydantic import BaseModel, Field


class SequenceRunStepCreate(BaseModel):
    """Request model for creating a sequence_run_step."""

    name: str = Field(..., min_length=1)
    run_id: str | None = Field(default=None)
    step_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)


class SequenceRunStepUpdate(BaseModel):
    """Request model for updating a sequence_run_step (all fields optional)."""

    name: str | None = Field(default=None)
    run_id: str | None = Field(default=None)
    step_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)


class SequenceRunStepResponse(BaseModel):
    """Response model for a sequence_run_step record."""

    id: str
    name: str
    run_id: str | None = None
    step_id: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str
    updated_at: str
