"""Source data models."""

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    """Request model for creating a source."""

    name: str = Field(..., min_length=1)
    type: str | None = Field(default=None)


class SourceUpdate(BaseModel):
    """Request model for updating a source (all fields optional)."""

    name: str | None = Field(default=None)
    type: str | None = Field(default=None)


class SourceResponse(BaseModel):
    """Response model for a source record."""

    id: str
    name: str
    type: str | None = None
    created_at: str
    updated_at: str
