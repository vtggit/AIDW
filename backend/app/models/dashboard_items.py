"""DashboardItem data models."""

from pydantic import BaseModel, Field


class DashboardItemCreate(BaseModel):
    """Request model for creating a dashboard_item."""

    dashboard_id: str | None = Field(default=None)
    source_suggestion_id: str | None = Field(default=None)
    title: str | None = Field(default=None)
    item_type: str | None = Field(default=None)
    aggregation: str | None = Field(default=None)
    position: int | None = Field(default=None)

    name: str = Field(..., min_length=1)


class DashboardItemUpdate(BaseModel):
    """Request model for updating a dashboard_item (all fields optional)."""

    dashboard_id: str | None = Field(default=None)
    source_suggestion_id: str | None = Field(default=None)
    title: str | None = Field(default=None)
    item_type: str | None = Field(default=None)
    aggregation: str | None = Field(default=None)
    position: int | None = Field(default=None)

    name: str | None = Field(default=None)


class DashboardItemResponse(BaseModel):
    """Response model for a dashboard_item record."""

    dashboard_id: str | None = None
    source_suggestion_id: str | None = None
    title: str | None = None
    item_type: str | None = None
    aggregation: str | None = None
    position: int | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
