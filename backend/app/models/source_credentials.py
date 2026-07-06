"""SourceCredential data models."""

from pydantic import BaseModel, Field


class SourceCredentialCreate(BaseModel):
    """Request model for creating a source_credential."""

    token_endpoint: str | None = Field(default=None)

    secret_ref: str | None = Field(default=None)

    source_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    auth_scheme: str | None = Field(default=None)
    principal: str | None = Field(default=None)


class SourceCredentialUpdate(BaseModel):
    """Request model for updating a source_credential (all fields optional)."""

    token_endpoint: str | None = Field(default=None)

    secret_ref: str | None = Field(default=None)

    source_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    auth_scheme: str | None = Field(default=None)
    principal: str | None = Field(default=None)


class SourceCredentialResponse(BaseModel):
    """Response model for a source_credential record."""

    token_endpoint: str | None = None

    secret_ref: str | None = None

    source_id: str | None = None

    id: str
    name: str
    auth_scheme: str | None = None
    principal: str | None = None
    created_at: str
    updated_at: str
