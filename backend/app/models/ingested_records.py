"""IngestedRecord data models (the CDC op-log)."""

from pydantic import BaseModel, Field


class IngestedRecordCreate(BaseModel):
    """Request model for creating an ingested_record."""

    run_id: str | None = Field(default=None)
    dataset_id: str | None = Field(default=None)
    business_key: str | None = Field(default=None)
    op: str | None = Field(default=None)
    ingested_at: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class IngestedRecordUpdate(BaseModel):
    """Request model for updating an ingested_record (all fields optional)."""

    run_id: str | None = Field(default=None)
    dataset_id: str | None = Field(default=None)
    business_key: str | None = Field(default=None)
    op: str | None = Field(default=None)
    ingested_at: str | None = Field(default=None)

    name: str | None = Field(default=None)


class IngestedRecordResponse(BaseModel):
    """Response model for an ingested_record record."""

    run_id: str | None = None
    dataset_id: str | None = None
    business_key: str | None = None
    op: str | None = None
    ingested_at: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
