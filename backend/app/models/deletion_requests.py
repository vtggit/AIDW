"""DeletionRequest data models."""

from pydantic import BaseModel, Field


class DeletionRequestCreate(BaseModel):
    """Request model for creating a deletion_request."""

    name: str = Field(..., min_length=1)
    subject_key: str | None = Field(default=None)
    subject_key_hash: str | None = Field(default=None)
    status: str | None = Field(default=None)
    reason: str | None = Field(default=None)
    error_detail: str | None = Field(default=None)
    attempts: int | None = Field(default=None)
    records_deleted: int | None = Field(default=None)
    profiles_cleared: int | None = Field(default=None)
    verified_by: str | None = Field(default=None)
    verified_at: str | None = Field(default=None)
    completed_at: str | None = Field(default=None)


class DeletionRequestUpdate(BaseModel):
    """Request model for updating a deletion_request (all fields optional)."""

    name: str | None = Field(default=None)
    subject_key: str | None = Field(default=None)
    subject_key_hash: str | None = Field(default=None)
    status: str | None = Field(default=None)
    reason: str | None = Field(default=None)
    error_detail: str | None = Field(default=None)
    attempts: int | None = Field(default=None)
    records_deleted: int | None = Field(default=None)
    profiles_cleared: int | None = Field(default=None)
    verified_by: str | None = Field(default=None)
    verified_at: str | None = Field(default=None)
    completed_at: str | None = Field(default=None)


class DeletionRequestResponse(BaseModel):
    """Response model for a deletion_request record."""

    id: str
    name: str
    subject_key: str | None = None
    subject_key_hash: str | None = None
    status: str | None = None
    reason: str | None = None
    error_detail: str | None = None
    attempts: int | None = None
    records_deleted: int | None = None
    profiles_cleared: int | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str
