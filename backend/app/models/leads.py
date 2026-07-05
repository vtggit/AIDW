"""Lead data models for the AICRM backend."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Allowed stage values — mirrored from the UI dropdown
ALLOWED_STAGES: set[str] = {
    "new",
    "contacted",
    "qualified",
    "proposal",
    "won",
    "lost",
}

# Allowed source values — mirrored from the UI dropdown
ALLOWED_SOURCES: set[str] = {
    "website",
    "referral",
    "social",
    "cold-call",
    "event",
}

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


class LeadCreate(BaseModel):
    """Request model for creating a lead."""

    company_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    value: float | None = Field(default=None, ge=0)
    stage: Literal["new", "contacted", "qualified", "proposal", "won", "lost"] = Field(
        default="new",
    )
    source: Literal["website", "referral", "social", "cold-call", "event"] | None = (
        Field(default=None)
    )
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class LeadUpdate(BaseModel):
    """Request model for updating a lead."""

    company_id: str | None = Field(default=None)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    value: float | None = Field(default=None, ge=0)
    stage: (
        Literal["new", "contacted", "qualified", "proposal", "won", "lost"] | None
    ) = Field(default=None)
    source: Literal["website", "referral", "social", "cold-call", "event"] | None = (
        Field(default=None)
    )
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class LeadResponse(BaseModel):
    """Response model for a lead record."""

    company_id: str | None = None

    id: str
    name: str
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    value: float | None = None
    stage: str = "new"
    source: str | None = None
    notes: str | None = None
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "name": "Acme Corp Lead",
                "company": "Acme Corp",
                "email": "lead@acme.com",
                "phone": "+1-555-0100",
                "value": 50000.0,
                "stage": "new",
                "source": "website",
                "notes": "Interested in enterprise plan",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        }
