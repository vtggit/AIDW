"""Suppression API models (#186)."""

from typing import Literal

from pydantic import BaseModel, Field


class SuppressionCreate(BaseModel):
    """Request model for adding a suppression entry."""

    email: str = Field(min_length=3, max_length=300)
    reason: Literal["unsubscribed", "hard_bounce", "complaint", "manual"]
    note: str | None = Field(default=None, max_length=500)


class SuppressionResponse(BaseModel):
    """A suppression entry."""

    id: str
    email: str
    reason: str
    note: str | None = None
    created_at: str

    class Config:
        from_attributes = True


class UnsubscribeRequest(BaseModel):
    """Admin-initiated unsubscribe of a contact (public intake lands with the ESP work)."""

    contact_id: str = Field(min_length=1, max_length=64)


class MaySendResponse(BaseModel):
    """The send-gate verdict every future send path must consult."""

    email: str
    may_send: bool
    reasons: list[str] = Field(default_factory=list)
