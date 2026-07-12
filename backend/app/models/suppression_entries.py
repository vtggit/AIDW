"""SuppressionEntry data models."""

from pydantic import BaseModel, Field


class SuppressionEntryCreate(BaseModel):
    """Request model for creating a suppression_entry."""

    name: str = Field(..., min_length=1)
    key_hash: str | None = Field(default=None)


class SuppressionEntryUpdate(BaseModel):
    """Request model for updating a suppression_entry (all fields optional)."""

    name: str | None = Field(default=None)
    key_hash: str | None = Field(default=None)


class SuppressionEntryResponse(BaseModel):
    """Response model for a suppression_entry record."""

    id: str
    name: str
    key_hash: str | None = None
    created_at: str
    updated_at: str
