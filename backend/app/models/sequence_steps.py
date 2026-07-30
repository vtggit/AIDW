"""SequenceStep data models."""

from pydantic import BaseModel, Field


class SequenceStepCreate(BaseModel):
    """Request model for creating a sequence_step."""

    order_index: int | None = Field(default=None)

    name: str = Field(..., min_length=1)
    sequence_id: str | None = Field(default=None)
    pipeline_id: str | None = Field(default=None)
    label: str | None = Field(default=None)


class SequenceStepUpdate(BaseModel):
    """Request model for updating a sequence_step (all fields optional)."""

    order_index: int | None = Field(default=None)

    name: str | None = Field(default=None)
    sequence_id: str | None = Field(default=None)
    pipeline_id: str | None = Field(default=None)
    label: str | None = Field(default=None)


class SequenceStepResponse(BaseModel):
    """Response model for a sequence_step record."""

    order_index: int | None = None

    id: str
    name: str
    sequence_id: str | None = None
    pipeline_id: str | None = None
    label: str | None = None
    created_at: str
    updated_at: str
