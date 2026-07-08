"""DeltaCursor data models."""

from pydantic import BaseModel, Field


class DeltaCursorCreate(BaseModel):
    """Request model for creating a delta_cursor."""

    pipeline_id: str | None = Field(default=None)
    cursor_field_id: str | None = Field(default=None)
    last_run_id: str | None = Field(default=None)
    cursor_kind: str | None = Field(default=None)
    cursor_value: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class DeltaCursorUpdate(BaseModel):
    """Request model for updating a delta_cursor (all fields optional)."""

    pipeline_id: str | None = Field(default=None)
    cursor_field_id: str | None = Field(default=None)
    last_run_id: str | None = Field(default=None)
    cursor_kind: str | None = Field(default=None)
    cursor_value: str | None = Field(default=None)

    name: str | None = Field(default=None)


class DeltaCursorResponse(BaseModel):
    """Response model for a delta_cursor record."""

    pipeline_id: str | None = None
    cursor_field_id: str | None = None
    last_run_id: str | None = None
    cursor_kind: str | None = None
    cursor_value: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
