"""Dataset data models."""

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    """Request model for creating a dataset."""

    first_seen_run_id: str | None = Field(default=None)

    source_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    object_type: str | None = Field(default=None)


class DatasetUpdate(BaseModel):
    """Request model for updating a dataset (all fields optional)."""

    first_seen_run_id: str | None = Field(default=None)

    source_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    object_type: str | None = Field(default=None)


class DatasetResponse(BaseModel):
    """Response model for a dataset record."""

    first_seen_run_id: str | None = None

    source_id: str | None = None

    id: str
    name: str
    object_type: str | None = None
    created_at: str
    updated_at: str
