"""ProcessStep data models."""

from pydantic import BaseModel, Field


class ProcessStepCreate(BaseModel):
    """Request model for creating a process_step."""

    name: str = Field(..., min_length=1)
    step_key: str | None = Field(default=None)
    ordinal: int | None = Field(default=None)
    step_type: str | None = Field(default=None)
    service_impl: str | None = Field(default=None)
    candidate_groups: str | None = Field(default=None)
    form_key: str | None = Field(default=None)
    timer_duration: int | None = Field(default=None)


class ProcessStepUpdate(BaseModel):
    """Request model for updating a process_step (all fields optional)."""

    name: str | None = Field(default=None)
    step_key: str | None = Field(default=None)
    ordinal: int | None = Field(default=None)
    step_type: str | None = Field(default=None)
    service_impl: str | None = Field(default=None)
    candidate_groups: str | None = Field(default=None)
    form_key: str | None = Field(default=None)
    timer_duration: int | None = Field(default=None)


class ProcessStepResponse(BaseModel):
    """Response model for a process_step record."""

    id: str
    name: str
    step_key: str | None = None
    ordinal: int | None = None
    step_type: str | None = None
    service_impl: str | None = None
    candidate_groups: str | None = None
    form_key: str | None = None
    timer_duration: int | None = None
    created_at: str
    updated_at: str
