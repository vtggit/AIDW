"""Activity data models for the AICRM backend."""

from typing import Literal

from pydantic import BaseModel, Field

# Allowed activity types — mirrored from the UI dropdown
ALLOWED_TYPES: set[str] = {"call", "email", "meeting", "note", "task"}

# Allowed activity statuses
ALLOWED_STATUSES: set[str] = {"pending", "completed"}


class ActivityCreate(BaseModel):
    """Request model for creating an activity."""

    type: Literal["call", "email", "meeting", "note", "task"] = Field(...)
    description: str = Field(..., min_length=1, max_length=5000)
    contact_name: str | None = Field(default=None, max_length=200)
    occurred_at: str | None = Field(default=None)
    due_date: str | None = Field(default=None)
    status: Literal["pending", "completed"] = Field(default="pending")


class ActivityUpdate(BaseModel):
    """Request model for updating an activity."""

    type: Literal["call", "email", "meeting", "note", "task"] | None = Field(
        default=None
    )
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    contact_name: str | None = Field(default=None, max_length=200)
    occurred_at: str | None = Field(default=None)
    due_date: str | None = Field(default=None)
    status: Literal["pending", "completed"] | None = Field(default=None)


class ActivityResponse(BaseModel):
    """Response model for an activity record."""

    id: str
    type: str
    description: str
    contact_name: str | None = None
    occurred_at: str
    due_date: str | None = None
    status: str = "pending"
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "type": "call",
                "description": "Follow-up call about proposal",
                "contact_name": "Jane Smith",
                "occurred_at": "2025-01-15T10:30:00+00:00",
                "due_date": "2025-01-20",
                "status": "pending",
                "created_at": "2025-01-15T10:30:00+00:00",
                "updated_at": "2025-01-15T10:30:00+00:00",
            }
        }
