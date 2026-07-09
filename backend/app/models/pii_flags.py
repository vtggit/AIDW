"""PiiFlag data models."""

from pydantic import BaseModel, Field


class PiiFlagCreate(BaseModel):
    """Request model for creating a pii_flag."""

    discovered_field_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    category: str | None = Field(default=None)
    detection_tier: str | None = Field(default=None)
    status: str | None = Field(default=None)
    confidence: float | None = Field(default=None)
    rationale: str | None = Field(default=None)
    fingerprint: str | None = Field(default=None)


class PiiFlagUpdate(BaseModel):
    """Request model for updating a pii_flag (all fields optional)."""

    discovered_field_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    category: str | None = Field(default=None)
    detection_tier: str | None = Field(default=None)
    status: str | None = Field(default=None)
    confidence: float | None = Field(default=None)
    rationale: str | None = Field(default=None)
    fingerprint: str | None = Field(default=None)


class PiiFlagResponse(BaseModel):
    """Response model for a pii_flag record."""

    discovered_field_id: str | None = None

    id: str
    name: str
    category: str | None = None
    detection_tier: str | None = None
    status: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    fingerprint: str | None = None
    created_at: str
    updated_at: str
