# Authentication-facing API endpoints

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.config import (
    AUTH_ALGORITHMS,
    AUTH_AUDIENCE,
    AUTH_CLIENT_ID,
    AUTH_ENABLED,
    AUTH_ISSUER,
    AUTH_JWKS_URL,
    AUTH_MODE,
)
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthConfigResponse(BaseModel):
    """Public auth configuration exposed to the frontend."""

    authEnabled: bool = Field(..., description="Whether authentication is enforced")
    authMode: str = Field(..., description="Current auth mode (development/production)")
    issuer: str | None = Field(default=None, description="IdP issuer URL")
    clientId: str | None = Field(default=None, description="OAuth client ID")
    audience: str | None = Field(default=None, description="Expected token audience")
    jwksUrl: str | None = Field(default=None, description="JWKS endpoint URL")
    algorithms: list[str] = Field(
        default_factory=list, description="Accepted JWT signature algorithms"
    )


@router.get("/me", response_model=MeResponse)
def get_me(current_user: AuthUser = Depends(require_authenticated_user)):
    """
    Return the currently authenticated user's context.

    Requires a valid Bearer token.  The response contains normalised
    roles and groups derived from the IdP token claims.  Used by the
    frontend to establish auth state at startup.
    """
    return MeResponse(authenticated=True, user=current_user)


@router.get("/config", response_model=AuthConfigResponse)
def get_auth_config():
    """
    Public (unauthenticated) endpoint that exposes non-sensitive frontend
    auth configuration.

    Only public client metadata is returned — no secrets, keys, or tokens.
    """
    return AuthConfigResponse(
        authEnabled=AUTH_ENABLED,
        authMode=AUTH_MODE,
        issuer=AUTH_ISSUER,
        clientId=AUTH_CLIENT_ID,
        audience=AUTH_AUDIENCE,
        jwksUrl=AUTH_JWKS_URL,
        algorithms=AUTH_ALGORITHMS,
    )
