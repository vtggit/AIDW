"""Contact data models for the AICRM backend."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Allowed status values — mirrored from the UI dropdown
ALLOWED_STATUSES: set[str] = {"active", "inactive", "vip"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str | None) -> str | None:
    """Raise if email is present but not plausibly formatted."""
    if value is None:
        return None
    if not _EMAIL_RE.match(value):
        raise ValueError("Email format is invalid.")
    return value


def _normalize_phone(value: str | None) -> str | None:
    """Strip everything except digits, '+', '-', '(', ')', and spaces."""
    if not value:
        return None
    return re.sub(r"[^\d+\-\(\)\s]", "", value)


class ContactCreate(BaseModel):
    """Request model for creating a contact."""

    company_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    status: Literal["active", "inactive", "vip"] = Field(default="active")
    notes: str | None = Field(default=None, max_length=5000)
    tag_ids: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class ContactUpdate(BaseModel):
    """Request model for updating a contact."""

    email_consent_status: Literal["opted_in", "opted_out", "unknown"] | None = None
    consent_source: str | None = Field(default=None, max_length=64)

    company_id: str | None = Field(default=None)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    status: Literal["active", "inactive", "vip"] | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=5000)
    tag_ids: list[str] | None = Field(default=None)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class ContactResponse(BaseModel):
    """Response model for a contact record."""

    email_consent_status: str = "unknown"
    consent_updated_at: str | None = None
    consent_source: str | None = None

    company_id: str | None = None

    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    status: str = "active"
    notes: str | None = None
    tags: list[dict] = Field(default_factory=list)
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "name": "Jane Smith",
                "email": "jane@example.com",
                "phone": "+1-555-0100",
                "company": "Acme Corp",
                "status": "active",
                "notes": "Met at conference",
                "tags": [{"id": "tag-1", "name": "Customer", "color": "#ef4444"}],
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        }


class BulkContactIds(BaseModel):
    """Request body for bulk contact operations."""

    ids: list[str] = Field(..., min_length=1, description="List of contact IDs")


class BulkStatusUpdate(BaseModel):
    """Request body for bulk status update."""

    ids: list[str] = Field(..., min_length=1, description="List of contact IDs")
    status: Literal["active", "inactive", "vip"] = Field(
        ..., description="New status for all contacts"
    )


class BulkOperationResult(BaseModel):
    """Response for bulk operations."""

    success_count: int
    message: str


class DuplicateContactResponse(BaseModel):
    """A single contact within a duplicate group."""

    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    status: str = "active"
    created_at: str
    updated_at: str


class DuplicateGroup(BaseModel):
    """A group of contacts that are duplicates of each other."""

    group_id: int
    match_type: str  # "email", "phone", or "name_company"
    contacts: list[DuplicateContactResponse]


class DuplicateDetectionResponse(BaseModel):
    """Response for the duplicate detection endpoint."""

    total_groups: int
    total_duplicates: int
    groups: list[DuplicateGroup]
