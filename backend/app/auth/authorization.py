# Simple application authorization helpers
#
# This is the first authorization layer — not a full RBAC engine.
# It provides FastAPI dependencies that enforce role-based access
# on top of an already-authenticated user.
#
# Usage:
#     @router.post("/contacts", dependencies=[Depends(require_role("admin"))])
#     def create_contact(...): ...

import logging

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.observability.logging import get_request_id

logger = logging.getLogger(__name__)


def _req() -> str:
    """Return a request-ID suffix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


# ---------------------------------------------------------------------------
# Application roles
#
# For now we recognise two roles:
#   "admin" — full access, including mutations
#   "user"  — read-only access (default for authenticated users)
# ---------------------------------------------------------------------------

ROLE_ADMIN = "admin"
ROLE_USER = "user"


def require_role(required_role: str):
    """
    Return a FastAPI dependency that enforces the caller holds
    *required_role*.

    * 401 — if the user is not authenticated (handled upstream)
    * 403 — if authenticated but missing the required role
    """

    def _check(
        current_user: AuthUser = Depends(require_authenticated_user),
    ) -> AuthUser:
        if required_role not in current_user.roles:
            logger.warning(
                "authz: forbidden — user %s lacks role '%s' (has %s)%s",
                current_user.sub,
                required_role,
                current_user.roles,
                _req(),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' is required to perform this action.",
            )
        return current_user

    return _check


def require_any_role(required_roles: list[str]):
    """
    Return a FastAPI dependency that enforces the caller holds
    at least one of *required_roles*.
    """

    def _check(
        current_user: AuthUser = Depends(require_authenticated_user),
    ) -> AuthUser:
        if not any(role in current_user.roles for role in required_roles):
            logger.warning(
                "authz: forbidden — user %s lacks any of %s (has %s)%s",
                current_user.sub,
                required_roles,
                current_user.roles,
                _req(),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of the following roles is required: {', '.join(required_roles)}.",
            )
        return current_user

    return _check
