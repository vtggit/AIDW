"""Run data models (the ingestion run spine)."""

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """Request model for creating a run."""

    rows_suppressed: int | None = Field(default=None)

    pipeline_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)
    rows_read: int | None = Field(default=None)
    rows_written: int | None = Field(default=None)
    error_detail: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class RunUpdate(BaseModel):
    """Request model for updating a run (all fields optional)."""

    rows_suppressed: int | None = Field(default=None)

    pipeline_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    trigger: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)
    rows_read: int | None = Field(default=None)
    rows_written: int | None = Field(default=None)
    error_detail: str | None = Field(default=None)

    name: str | None = Field(default=None)


class RunResponse(BaseModel):
    """Response model for a run record."""

    rows_suppressed: int | None = None

    pipeline_id: str | None = None
    status: str | None = None
    trigger: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    rows_read: int | None = None
    rows_written: int | None = None
    error_detail: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
