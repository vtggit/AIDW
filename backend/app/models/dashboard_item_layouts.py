"""DashboardItemLayout data models."""

from pydantic import BaseModel, Field


class DashboardItemLayoutCreate(BaseModel):
    """Request model for creating a dashboard_item_layout.

    user_id is intentionally absent — it is derived from the caller's
    authentication token and must never be supplied by the client.
    """

    grid_row_span: int | None = Field(default=None, ge=1, le=6)

    grid_col_start: int | None = Field(default=None, gt=0)

    grid_col_span: int | None = Field(default=None, ge=1, le=12)

    name: str = Field(..., min_length=1)
    dashboard_item_id: str | None = Field(default=None)


class DashboardItemLayoutUpdate(BaseModel):
    """Request model for updating a dashboard_item_layout (all fields optional).

    user_id is kept as an accepted-but-ignored field so that clients sending it
    do not receive a 422; the service layer strips it before persistence.
    """

    grid_row_span: int | None = Field(default=None, ge=1, le=6)

    grid_col_start: int | None = Field(default=None, gt=0)

    grid_col_span: int | None = Field(default=None, ge=1, le=12)

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
