"""LoadSequence data models."""

from pydantic import BaseModel, Field


class LoadSequenceCreate(BaseModel):
    """Request model for creating a load_sequence."""

    name: str = Field(..., min_length=1)
    description: str | None = Field(default=None)


class LoadSequenceUpdate(BaseModel):
    """Request model for updating a load_sequence (all fields optional)."""

    name: str | None = Field(default=None)
    description: str | None = Field(default=None)


class LoadSequenceResponse(BaseModel):
    """Response model for a load_sequence record."""

    id: str
    name: str
    description: str | None = None
    created_at: str
    updated_at: str
