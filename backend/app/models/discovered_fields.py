"""DiscoveredField data models."""

from pydantic import BaseModel, Field


class DiscoveredFieldCreate(BaseModel):
    """Request model for creating a discovered_field."""

    name: str = Field(..., min_length=1)
    data_type: str | None = Field(default=None)


class DiscoveredFieldUpdate(BaseModel):
    """Request model for updating a discovered_field (all fields optional)."""

    name: str | None = Field(default=None)
    data_type: str | None = Field(default=None)


class DiscoveredFieldResponse(BaseModel):
    """Response model for a discovered_field record."""

    id: str
    name: str
    data_type: str | None = None
    created_at: str
    updated_at: str
