"""Settings data models for the AICRM backend.

Settings are treated as a single application-level configuration object.
The payload is a JSON blob preserving whatever fields the UI already uses
(theme, lastBackup, etc.) without inventing a new taxonomy.
"""

from typing import Any

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    """Request model for updating settings.

    Accepts a free-form dict of key/value pairs so the UI can send
    whatever fields it currently manages without backend changes.
    """

    payload: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    """Response model for the current settings record."""

    id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "app",
                "payload": {"theme": "light", "lastBackup": "2025-01-01T00:00:00"},
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        }
