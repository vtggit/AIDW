"""DashboardItemField data models."""

from pydantic import BaseModel, Field


class DashboardItemFieldCreate(BaseModel):
    """Request model for creating a dashboard_item_field."""

    dashboard_item_id: str | None = Field(default=None)
    discovered_field_id: str | None = Field(default=None)
    field_role: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class DashboardItemFieldUpdate(BaseModel):
    """Request model for updating a dashboard_item_field (all fields optional)."""

    dashboard_item_id: str | None = Field(default=None)
    discovered_field_id: str | None = Field(default=None)
    field_role: str | None = Field(default=None)

    name: str | None = Field(default=None)


class DashboardItemFieldResponse(BaseModel):
    """Response model for a dashboard_item_field record."""

    dashboard_item_id: str | None = None
    discovered_field_id: str | None = None
    field_role: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
