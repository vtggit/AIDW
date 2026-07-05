"""Template data models for the AICRM backend."""

from typing import Literal

from pydantic import BaseModel, Field

# Allowed category values — mirrored from the UI dropdown
ALLOWED_CATEGORIES: set[str] = {
    "follow-up",
    "introduction",
    "proposal",
    "thank-you",
    "meeting",
    "other",
}


class TemplateCreate(BaseModel):
    """Request model for creating a template."""

    name: str = Field(..., min_length=1, max_length=200)
    category: Literal[
        "follow-up", "introduction", "proposal", "thank-you", "meeting", "other"
    ] = Field(default="other")
    subject: str | None = Field(default=None, max_length=500)
    content: str = Field(..., min_length=1)


class TemplateUpdate(BaseModel):
    """Request model for updating a template."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: (
        Literal[
            "follow-up", "introduction", "proposal", "thank-you", "meeting", "other"
        ]
        | None
    ) = Field(default=None)
    subject: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None)


class TemplateResponse(BaseModel):
    """Response model for a template record."""

    id: str
    name: str
    category: str = "other"
    subject: str | None = None
    content: str | None = None
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "name": "Welcome Email",
                "category": "introduction",
                "subject": "Welcome to {{contact_company}}!",
                "content": "Dear {{contact_name}}, thank you for joining us.",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        }
