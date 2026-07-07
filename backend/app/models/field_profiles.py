"""FieldProfile data models."""

from pydantic import BaseModel, Field


class FieldProfileCreate(BaseModel):
    """Request model for creating a field_profile."""

    discovered_field_id: str | None = Field(default=None)
    row_count: int | None = Field(default=None)
    null_count: int | None = Field(default=None)
    distinct_count: int | None = Field(default=None)
    min_value: str | None = Field(default=None)
    max_value: str | None = Field(default=None)
    most_common_value: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class FieldProfileUpdate(BaseModel):
    """Request model for updating a field_profile (all fields optional)."""

    discovered_field_id: str | None = Field(default=None)
    row_count: int | None = Field(default=None)
    null_count: int | None = Field(default=None)
    distinct_count: int | None = Field(default=None)
    min_value: str | None = Field(default=None)
    max_value: str | None = Field(default=None)
    most_common_value: str | None = Field(default=None)

    name: str | None = Field(default=None)


class FieldProfileResponse(BaseModel):
    """Response model for a field_profile record."""

    discovered_field_id: str | None = None
    row_count: int | None = None
    null_count: int | None = None
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    most_common_value: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
