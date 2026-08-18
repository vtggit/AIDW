"""FeedCredential data models."""

from pydantic import BaseModel, Field


class FeedCredentialCreate(BaseModel):
    """Request model for creating a feed_credential."""

    name: str = Field(..., min_length=1)
    principal: str | None = Field(default=None)
    key_hash: str | None = Field(default=None)
    key_prefix: str | None = Field(default=None)
    revoked: bool | None = Field(default=None)


class FeedCredentialUpdate(BaseModel):
    """Request model for updating a feed_credential (all fields optional)."""

    name: str | None = Field(default=None)
    principal: str | None = Field(default=None)
    key_hash: str | None = Field(default=None)
    key_prefix: str | None = Field(default=None)
    revoked: bool | None = Field(default=None)


class FeedCredentialResponse(BaseModel):
    """Response model for a feed_credential record."""

    id: str
    name: str
    principal: str | None = None
    key_hash: str | None = None
    key_prefix: str | None = None
    revoked: bool | None = None
    created_at: str
    updated_at: str
