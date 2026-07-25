"""DashboardItemLayout data models."""

from pydantic import BaseModel, Field


class DashboardItemLayoutCreate(BaseModel):
    """Request model for creating a dashboard_item_layout."""

    grid_row_span: int | None = Field(default=None)

    grid_col_start: int | None = Field(default=None)

    grid_col_span: int | None = Field(default=None)

    name: str = Field(..., min_length=1)
    user_id: str | None = Field(default=None)
    dashboard_item_id: str | None = Field(default=None)


class DashboardItemLayoutUpdate(BaseModel):
    """Request model for updating a dashboard_item_layout (all fields optional)."""

    grid_row_span: int | None = Field(default=None)

    grid_col_start: int | None = Field(default=None)

    grid_col_span: int | None = Field(default=None)

    name: str | None = Field(default=None)
    user_id: str | None = Field(default=None)
    dashboard_item_id: str | None = Field(default=None)


class DashboardItemLayoutResponse(BaseModel):
    """Response model for a dashboard_item_layout record."""

    grid_row_span: int | None = None

    grid_col_start: int | None = None

    grid_col_span: int | None = None

    id: str
    name: str
    user_id: str | None = None
    dashboard_item_id: str | None = None
    created_at: str
    updated_at: str
