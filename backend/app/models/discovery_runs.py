"""DiscoveryRun data models."""

from pydantic import BaseModel, Field


class DiscoveryRunCreate(BaseModel):
    """Request model for creating a discovery_run."""

    name: str = Field(..., min_length=1)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)


class DiscoveryRunUpdate(BaseModel):
    """Request model for updating a discovery_run (all fields optional)."""

    name: str | None = Field(default=None)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)


class DiscoveryRunResponse(BaseModel):
    """Response model for a discovery_run record."""

    id: str
    name: str
    status: str | None = None
    trigger: str | None = None
    created_at: str
    updated_at: str
