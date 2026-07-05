# FastAPI route dependencies for authentication
#
# These are the gatekeepers — every protected route should declare one of
# these as a dependency.  Route handlers never touch tokens directly.

import logging

from fastapi import Depends, Header, HTTPException, status

from app.auth.config import AUTH_ENABLED
from app.auth.models import AuthUser
from app.auth.security import validate_token
from app.observability.logging import get_request_id

logger = logging.getLogger(__name__)


def _req() -> str:
    """Return a request-ID suffix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


def _extract_bearer_token(authorization: str | None = None) -> str | None:
    """
    Pull the raw token string out of an ``Authorization: Bearer <token>``
    header.  Returns ``None`` when the header is absent or malformed.
    """
    if not authorization:
        logger.warning("auth: missing Authorization header%s", _req())
        return None
    parts = authorization.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    logger.warning("auth: malformed Authorization header%s", _req())
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
) -> AuthUser | None:
    """
    Optional authentication dependency.

    Returns the ``AuthUser`` when a valid token is present, or ``None``
    when no token is supplied.  Useful for routes that *can* work
    anonymously but want to know who the caller is when authenticated.
    """
    if not AUTH_ENABLED:
        # Auth disabled — return a synthetic "anonymous" user
        return AuthUser(
            sub="anonymous",
            username="anonymous",
            roles=[],
            groups=[],
            raw_claims={"mode": "auth-disabled"},
        )

    token = _extract_bearer_token(authorization)
    if not token:
        return None

    user = validate_token(token)
    return user


def require_authenticated_user(
    current_user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    """
    Mandatory authentication dependency.

    If the caller is not authenticated, FastAPI returns 401 Unauthorized
    before the route handler is ever invoked.  Use this on every route
    that must require a valid identity.

    The response includes an ``auth_failure_reason`` field to help
    distinguish between missing token, invalid token, and expired token.
    """
    if current_user is None:
        logger.warning("auth: unauthenticated access attempt%s", _req())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user
