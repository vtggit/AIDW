"""Sales goals and quota tracking data models."""

from typing import Literal

from pydantic import BaseModel, Field


class SalesGoalCreate(BaseModel):
    """Request model for creating a sales goal."""

    name: str = Field(..., min_length=1, max_length=200)
    type: Literal["revenue", "deals", "contacts", "activities"] = Field(...)
    target_value: float = Field(..., gt=0)
    period: Literal["monthly", "quarterly", "yearly"] = Field(...)
    start_date: str = Field(..., min_length=1)
    end_date: str = Field(..., min_length=1)


class SalesGoalUpdate(BaseModel):
    """Request model for updating a sales goal."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    target_value: float | None = Field(default=None, gt=0)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)


class SalesGoalResponse(BaseModel):
    """Response model for a sales goal record."""

    id: str
    name: str
    type: str
    target_value: float
    current_value: float = 0.0
    period: str
    start_date: str
    end_date: str
    progress_percent: float = 0.0
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "goal-001",
                "name": "Q1 Revenue Target",
                "type": "revenue",
                "target_value": 500000.0,
                "current_value": 325000.0,
                "period": "quarterly",
                "start_date": "2025-01-01",
                "end_date": "2025-03-31",
                "progress_percent": 65.0,
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        }


class SalesGoalProgress(BaseModel):
    """Progress summary for all active goals."""

    goals: list[SalesGoalResponse] = []
    overall_progress: float = 0.0
