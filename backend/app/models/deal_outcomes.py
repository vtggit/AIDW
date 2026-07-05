"""Deal outcome data models for win/loss reason tracking."""

from typing import Literal

from pydantic import BaseModel, Field

# Allowed reason categories — mirrored from the UI
ALLOWED_REASON_CATEGORIES: set[str] = {
    "budget",
    "competitor",
    "feature-gap",
    "timing",
    "decision-changed",
    "internal-issues",
    "other",
}


class DealOutcomeCreate(BaseModel):
    """Request model for creating a deal outcome (win/loss reason)."""

    lead_id: str = Field(..., min_length=1)
    outcome: Literal["won", "lost"] = Field(...)
    reason_category: Literal[
        "budget",
        "competitor",
        "feature-gap",
        "timing",
        "decision-changed",
        "internal-issues",
        "other",
    ] = Field(...)
    reason_text: str | None = Field(default=None, max_length=2000)
    competitor_name: str | None = Field(default=None, max_length=200)


class DealOutcomeUpdate(BaseModel):
    """Request model for updating a deal outcome."""

    reason_category: (
        Literal[
            "budget",
            "competitor",
            "feature-gap",
            "timing",
            "decision-changed",
            "internal-issues",
            "other",
        ]
        | None
    ) = Field(default=None)
    reason_text: str | None = Field(default=None, max_length=2000)
    competitor_name: str | None = Field(default=None, max_length=200)


class DealOutcomeResponse(BaseModel):
    """Response model for a deal outcome record."""

    id: str
    lead_id: str
    outcome: str
    reason_category: str
    reason_text: str | None = None
    competitor_name: str | None = None
    created_at: str
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "lead_id": "lead-456",
                "outcome": "won",
                "reason_category": "budget",
                "reason_text": "Client had ample budget for enterprise plan",
                "competitor_name": None,
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        }


class DealOutcomeAnalytics(BaseModel):
    """Analytics summary for deal outcomes."""

    total_won: int = 0
    total_lost: int = 0
    win_rate: float = 0.0
    top_win_reasons: list[dict[str, object]] = []
    top_loss_reasons: list[dict[str, object]] = []
    competitor_mentions: list[dict[str, object]] = []
