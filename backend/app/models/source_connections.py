"""SourceConnection data models."""

from pydantic import BaseModel, Field


class SourceConnectionCreate(BaseModel):
    """Request model for creating a source_connection."""

    source_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    endpoint: str | None = Field(default=None)
    protocol_version: str | None = Field(default=None)


class SourceConnectionUpdate(BaseModel):
    """Request model for updating a source_connection (all fields optional)."""

    source_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    endpoint: str | None = Field(default=None)
    protocol_version: str | None = Field(default=None)


class SourceConnectionResponse(BaseModel):
    """Response model for a source_connection record."""

    source_id: str | None = None

    id: str
    name: str
    endpoint: str | None = None
    protocol_version: str | None = None
    created_at: str
    updated_at: str
