"""Health check API route.

Provides two levels of health information:

1. GET /api/health — Shallow liveness check (no dependency calls).
   Returns app status, version, and build metadata. Suitable for
   load balancers and container liveness probes.

2. GET /api/health/ready — Readiness check including dependency status.
   Tests database connectivity and reports dependency health. Suitable
   for container readiness probes and operational diagnostics.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import APP_VERSION, BUILD_TIMESTAMP, GIT_SHA

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    """Status of a single dependency (e.g. database)."""

    name: str = Field(..., description="Dependency name")
    status: str = Field(..., description="ok, error, or unavailable")
    detail: str | None = Field(default=None, description="Optional diagnostic detail")


class HealthResponse(BaseModel):
    """Response model for the shallow health check endpoint."""

    status: str = Field(..., description="Service health status")
    app_version: str = Field(..., description="Application version string")
    service: str = Field(..., description="Service identifier")
    git_sha: str | None = Field(
        default=None, description="Git commit SHA (build metadata)"
    )
    build_timestamp: str | None = Field(
        default=None, description="ISO-8601 build timestamp (build metadata)"
    )


class ReadinessResponse(BaseModel):
    """Response model for the readiness health check endpoint."""

    status: str = Field(..., description="Service readiness status")
    app_version: str = Field(..., description="Application version string")
    service: str = Field(..., description="Service identifier")
    git_sha: str | None = Field(
        default=None, description="Git commit SHA (build metadata)"
    )
    build_timestamp: str | None = Field(
        default=None, description="ISO-8601 build timestamp (build metadata)"
    )
    dependencies: list[DependencyStatus] = Field(
        default_factory=list, description="Status of critical dependencies"
    )


def _check_database() -> DependencyStatus:
    """Test database connectivity and return a DependencyStatus."""
    try:
        from app.db.connection import get_connection

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        finally:
            conn.close()
        return DependencyStatus(name="database", status="ok")
    except Exception as exc:
        logger.error("health: database check failed — %s", exc)
        return DependencyStatus(
            name="database",
            status="error",
            detail=str(exc),
        )


@router.get("/api/health", response_model=HealthResponse)
def health_check():
    """Shallow liveness check — does not call dependencies.

    Returns app status, version, and build metadata.
    Use this for load balancer health checks and container liveness probes.
    """
    payload: dict = {
        "status": "ok",
        "app_version": APP_VERSION,
        "service": "aicrm-backend",
    }
    if GIT_SHA:
        payload["git_sha"] = GIT_SHA
    if BUILD_TIMESTAMP:
        payload["build_timestamp"] = BUILD_TIMESTAMP
    return payload


@router.get("/api/health/ready", response_model=ReadinessResponse)
def readiness_check():
    """Readiness check — verifies critical dependencies are reachable.

    Tests database connectivity and reports dependency health.
    Returns status 'ok' only when all dependencies are healthy.
    Use this for container readiness probes and operational diagnostics.
    """
    dependencies: list[DependencyStatus] = [_check_database()]

    overall_status = "ok"
    for dep in dependencies:
        if dep.status != "ok":
            overall_status = "degraded"
            break

    payload: dict = {
        "status": overall_status,
        "app_version": APP_VERSION,
        "service": "aicrm-backend",
        "dependencies": dependencies,
    }
    if GIT_SHA:
        payload["git_sha"] = GIT_SHA
    if BUILD_TIMESTAMP:
        payload["build_timestamp"] = BUILD_TIMESTAMP
    return payload


@router.get("/api/health/version")
def route_api_health_version():
    return {"version": APP_VERSION}
