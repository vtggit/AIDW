"""FeedCredential data models."""

from pydantic import BaseModel, ConfigDict, Field


class FeedCredentialCreate(BaseModel):
    """Request model for creating a feed_credential.

    Unknown fields are rejected: ``last_used_at`` is written exclusively by
    the authentication path and cannot be set through the create route.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    principal: str | None = Field(default=None)
    key_hash: str | None = Field(default=None)
    key_prefix: str | None = Field(default=None)
    revoked: bool | None = Field(default=None)


class FeedCredentialUpdate(BaseModel):
    """Request model for updating a feed_credential (all fields optional).

    Unknown fields are rejected: ``last_used_at`` is written exclusively by
    the authentication path and cannot be set through the update route.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None)
    principal: str | None = Field(default=None)
    key_hash: str | None = Field(default=None)
    key_prefix: str | None = Field(default=None)
    revoked: bool | None = Field(default=None)


class FeedCredentialResponse(BaseModel):
    """Response model for a feed_credential record.

    ``key_hash`` is intentionally absent: key material is never returned to
    any caller, admin included.
    """

    id: str
    name: str
    principal: str | None = None
    key_prefix: str | None = None
    revoked: bool | None = None
    created_at: str
    updated_at: str
    last_used_at: str | None = None
