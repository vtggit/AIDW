"""Dashboard data models."""

from pydantic import BaseModel, Field


class DashboardCreate(BaseModel):
    """Request model for creating a dashboard."""

    grid_columns: int | None = Field(default=None)

    description: str | None = Field(default=None)

    name: str = Field(..., min_length=1)


class DashboardUpdate(BaseModel):
    """Request model for updating a dashboard (all fields optional)."""

    grid_columns: int | None = Field(default=None)

    description: str | None = Field(default=None)

    name: str | None = Field(default=None)


class DashboardResponse(BaseModel):
    """Response model for a dashboard record."""

    grid_columns: int | None = None

    description: str | None = None

    id: str
    name: str
    created_at: str
    updated_at: str
