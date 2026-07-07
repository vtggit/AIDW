"""SuggestionField data models."""

from pydantic import BaseModel, Field


class SuggestionFieldCreate(BaseModel):
    """Request model for creating a suggestion_field."""

    suggestion_id: str | None = Field(default=None)
    discovered_field_id: str | None = Field(default=None)
    field_role: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class SuggestionFieldUpdate(BaseModel):
    """Request model for updating a suggestion_field (all fields optional)."""

    suggestion_id: str | None = Field(default=None)
    discovered_field_id: str | None = Field(default=None)
    field_role: str | None = Field(default=None)

    name: str | None = Field(default=None)


class SuggestionFieldResponse(BaseModel):
    """Response model for a suggestion_field record."""

    suggestion_id: str | None = None
    discovered_field_id: str | None = None
    field_role: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
