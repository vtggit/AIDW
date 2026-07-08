"""Pipeline data models."""

from pydantic import BaseModel, Field


class PipelineCreate(BaseModel):
    """Request model for creating a pipeline."""

    dataset_id: str | None = Field(default=None)
    cdc_pattern: str | None = Field(default=None)
    schedule: str | None = Field(default=None)
    is_enabled: bool | None = Field(default=None)

    name: str = Field(..., min_length=1)


class PipelineUpdate(BaseModel):
    """Request model for updating a pipeline (all fields optional)."""

    dataset_id: str | None = Field(default=None)
    cdc_pattern: str | None = Field(default=None)
    schedule: str | None = Field(default=None)
    is_enabled: bool | None = Field(default=None)

    name: str | None = Field(default=None)


class PipelineResponse(BaseModel):
    """Response model for a pipeline record."""

    dataset_id: str | None = None
    cdc_pattern: str | None = None
    schedule: str | None = None
    is_enabled: bool | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
