"""Suggestion data models."""

from pydantic import BaseModel, Field


class SuggestionCreate(BaseModel):
    """Request model for creating a suggestion."""

    dataset_id: str | None = Field(default=None)
    title: str | None = Field(default=None)
    item_type: str | None = Field(default=None)
    aggregation: str | None = Field(default=None)
    score: float | None = Field(default=None)
    rationale: str | None = Field(default=None)
    strategy: str | None = Field(default=None)
    status: str | None = Field(default=None)
    fingerprint: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class SuggestionUpdate(BaseModel):
    """Request model for updating a suggestion (all fields optional)."""

    dataset_id: str | None = Field(default=None)
    title: str | None = Field(default=None)
    item_type: str | None = Field(default=None)
    aggregation: str | None = Field(default=None)
    score: float | None = Field(default=None)
    rationale: str | None = Field(default=None)
    strategy: str | None = Field(default=None)
    status: str | None = Field(default=None)
    fingerprint: str | None = Field(default=None)

    name: str | None = Field(default=None)


class SuggestionResponse(BaseModel):
    """Response model for a suggestion record."""

    dataset_id: str | None = None
    title: str | None = None
    item_type: str | None = None
    aggregation: str | None = None
    score: float | None = None
    rationale: str | None = None
    strategy: str | None = None
    status: str | None = None
    fingerprint: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
