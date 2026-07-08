"""DiscoveredField data models."""

from pydantic import BaseModel, Field


class DiscoveredFieldCreate(BaseModel):
    """Request model for creating a discovered_field."""

    first_seen_run_id: str | None = Field(default=None)

    field_position: int | None = Field(default=None)

    is_key: bool | None = Field(default=None)

    is_nullable: bool | None = Field(default=None)

    dataset_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    data_type: str | None = Field(default=None)


class DiscoveredFieldUpdate(BaseModel):
    """Request model for updating a discovered_field (all fields optional)."""

    first_seen_run_id: str | None = Field(default=None)

    field_position: int | None = Field(default=None)

    is_key: bool | None = Field(default=None)

    is_nullable: bool | None = Field(default=None)

    dataset_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    data_type: str | None = Field(default=None)


class DiscoveredFieldResponse(BaseModel):
    """Response model for a discovered_field record."""

    first_seen_run_id: str | None = None

    field_position: int | None = None

    is_key: bool | None = None

    is_nullable: bool | None = None

    dataset_id: str | None = None

    id: str
    name: str
    data_type: str | None = None
    created_at: str
    updated_at: str
