"""Widget data models."""

from pydantic import BaseModel, Field


class WidgetCreate(BaseModel):
    """Request model for creating a widget."""

    name: str = Field(..., min_length=1)
    label: str | None = Field(default=None)


class WidgetUpdate(BaseModel):
    """Request model for updating a widget (all fields optional)."""

    name: str | None = Field(default=None)
    label: str | None = Field(default=None)


class WidgetResponse(BaseModel):
    """Response model for a widget record."""

    id: str
    name: str
    label: str | None = None
    created_at: str
    updated_at: str
