"""ConnectionTest data models."""

from pydantic import BaseModel, Field


class ConnectionTestCreate(BaseModel):
    """Request model for creating a connection_test."""

    latency_ms: int | None = Field(default=None)

    source_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    status: str | None = Field(default=None)
    message: str | None = Field(default=None)


class ConnectionTestUpdate(BaseModel):
    """Request model for updating a connection_test (all fields optional)."""

    latency_ms: int | None = Field(default=None)

    source_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    status: str | None = Field(default=None)
    message: str | None = Field(default=None)


class ConnectionTestResponse(BaseModel):
    """Response model for a connection_test record."""

    latency_ms: int | None = None

    source_id: str | None = None

    id: str
    name: str
    status: str | None = None
    message: str | None = None
    created_at: str
    updated_at: str
