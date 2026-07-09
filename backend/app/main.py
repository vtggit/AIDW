"""AICRM FastAPI application factory.

Startup behavior:
    1. Bootstrap structured logging
    2. Register middleware (request ID, request logging, CORS)
    3. Register global exception handlers for operational clarity
    4. Mount all API routers
    5. Log startup confirmation

Failure behavior:
    - Database connection errors during requests return 503 with a clear message
    - All unhandled exceptions return 500 with request ID for tracing
"""

import logging

import psycopg2
import psycopg2.errors
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import APP_NAME, APP_VERSION, CORS_ORIGINS
from app.observability.logging import setup_logging
from app.observability.middleware import (
    RequestIDMiddleware,
    RequestLoggingMiddleware,
)

# ---------------------------------------------------------------------------
# Bootstrap logging before anything else runs
# ---------------------------------------------------------------------------
setup_logging()

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory — returns a configured FastAPI instance.

    Exists primarily so tests can create isolated app instances after
    mutating environment variables.  The module-level ``app`` variable
    calls this factory for normal startup.
    """
    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
    )

    # Request correlation — must be added before CORS so it wraps every request
    application.add_middleware(RequestIDMiddleware)

    # Per-request logging — logs method, path, status, and duration
    application.add_middleware(RequestLoggingMiddleware)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Global exception handlers for operational clarity
    # -----------------------------------------------------------------------

    @application.exception_handler(psycopg2.errors.ForeignKeyViolation)
    async def foreign_key_violation_handler(
        request: Request, exc: psycopg2.errors.ForeignKeyViolation
    ):
        """A write referenced a missing row (SQLSTATE 23503).

        Returns a structured 422 naming the invalid reference (from the
        driver diagnostics) instead of the generic 5xx database error.
        Starlette resolves handlers by MRO, so this specific handler wins
        over the generic ``psycopg2.Error`` -> 503 handler below.
        """
        from app.observability.logging import get_request_id

        request_id = get_request_id()
        diag = getattr(exc, "diag", None)
        reference = (
            getattr(diag, "message_detail", None)
            or getattr(diag, "constraint_name", None)
            or "a foreign key constraint was violated"
        )
        logger.warning(
            "invalid reference during request %s %s — %s request_id=%s",
            request.method,
            request.url.path,
            reference,
            request_id,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Invalid reference: {reference}",
                "request_id": request_id,
            },
        )

    @application.exception_handler(psycopg2.errors.UniqueViolation)
    async def unique_violation_handler(
        request: Request, exc: psycopg2.errors.UniqueViolation
    ):
        """A write violated a unique constraint (SQLSTATE 23505).

        Returns 409 Conflict naming the duplicate (from the driver
        diagnostics) instead of the generic 5xx database error.
        """
        from app.observability.logging import get_request_id

        request_id = get_request_id()
        diag = getattr(exc, "diag", None)
        duplicate = (
            getattr(diag, "message_detail", None)
            or getattr(diag, "constraint_name", None)
            or "a unique constraint was violated"
        )
        logger.warning(
            "duplicate value during request %s %s — %s request_id=%s",
            request.method,
            request.url.path,
            duplicate,
            request_id,
        )
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"Duplicate value: {duplicate}",
                "request_id": request_id,
            },
        )

    @application.exception_handler(psycopg2.errors.CheckViolation)
    async def check_violation_handler(
        request: Request, exc: psycopg2.errors.CheckViolation
    ):
        """A write violated a CHECK constraint (SQLSTATE 23514) — e.g. an out-of-enum value.

        That is a bad-input (client) error, so return 422 naming the constraint (from the driver
        diagnostics) instead of the generic 5xx. More specific than the ``psycopg2.Error`` handler
        below, so Starlette's MRO resolution picks this one.
        """
        from app.observability.logging import get_request_id

        request_id = get_request_id()
        diag = getattr(exc, "diag", None)
        constraint = (
            getattr(diag, "constraint_name", None)
            or getattr(diag, "message_primary", None)
            or "a check constraint was violated"
        )
        logger.warning(
            "check violation during request %s %s — %s request_id=%s",
            request.method,
            request.url.path,
            constraint,
            request_id,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Invalid value: {constraint}",
                "request_id": request_id,
            },
        )

    @application.exception_handler(psycopg2.Error)
    async def database_error_handler(request: Request, exc: psycopg2.Error):
        """Handle PostgreSQL connection and query errors.

        Returns 503 Service Unavailable with a clear message.
        The request ID is included for tracing.
        """
        from app.observability.logging import get_request_id

        request_id = get_request_id()
        logger.error(
            "database error during request %s %s — %s request_id=%s",
            request.method,
            request.url.path,
            exc,
            request_id,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database service is currently unavailable. Please try again later.",
                "request_id": request_id,
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Handle FastAPI request validation errors with consistent formatting."""
        from app.observability.logging import get_request_id

        request_id = get_request_id()
        errors = []
        for error in exc.errors():
            errors.append(
                {
                    "field": ".".join(str(loc) for loc in error.get("loc", [])),
                    "message": error.get("msg", ""),
                    "type": error.get("type", ""),
                }
            )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed.",
                "errors": errors,
                "request_id": request_id,
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        """Catch-all for unhandled exceptions.

        Returns 500 Internal Server Error with request ID for tracing.
        Never leaks internal details to the client.
        """
        from app.observability.logging import get_request_id

        request_id = get_request_id()
        logger.exception(
            "unhandled exception during request %s %s — %s request_id=%s",
            request.method,
            request.url.path,
            exc,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred. Please try again later.",
                "request_id": request_id,
            },
        )

    # Import routers inside the factory so they capture the current
    # app instance when reloaded between tests.
    from app.api.audit import router as audit_router
    from app.api.auth import router as auth_router
    from app.api.connection_tests import router as connection_tests_router
    from app.api.dashboard_item_fields import router as dashboard_item_fields_router
    from app.api.dashboard_items import router as dashboard_items_router
    from app.api.dashboards import router as dashboards_router
    from app.api.datasets import router as datasets_router
    from app.api.delta_cursors import router as delta_cursors_router
    from app.api.discovered_fields import router as discovered_fields_router
    from app.api.discovery import router as discovery_router
    from app.api.discovery_runs import router as discovery_runs_router
    from app.api.field_profiles import router as field_profiles_router
    from app.api.health import router as health_router
    from app.api.ingest import router as ingest_router
    from app.api.ingested_records import router as ingested_records_router
    from app.api.odata_service_configs import router as odata_service_configs_router
    from app.api.pii_decisions import flags_router as pii_decisions_router
    from app.api.pii_decisions import scan_router as pii_scan_router
    from app.api.pii_flags import router as pii_flags_router
    from app.api.pipelines import router as pipelines_router
    from app.api.profiling import router as profiling_router
    from app.api.runs import router as runs_router
    from app.api.source_connections import router as source_connections_router
    from app.api.source_credentials import router as source_credentials_router
    from app.api.sources import router as sources_router
    from app.api.suggestion_fields import router as suggestion_fields_router
    from app.api.suggestions import router as suggestions_router

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(audit_router)
    application.include_router(sources_router)
    application.include_router(datasets_router)
    application.include_router(discovery_router)
    application.include_router(discovered_fields_router)
    application.include_router(source_connections_router)
    application.include_router(source_credentials_router)
    application.include_router(odata_service_configs_router)
    application.include_router(connection_tests_router)
    application.include_router(suggestions_router)
    application.include_router(suggestion_fields_router)
    application.include_router(dashboards_router)
    application.include_router(dashboard_items_router)
    application.include_router(dashboard_item_fields_router)
    application.include_router(profiling_router)
    application.include_router(field_profiles_router)
    application.include_router(pipelines_router)
    application.include_router(runs_router)
    application.include_router(delta_cursors_router)
    application.include_router(ingested_records_router)
    application.include_router(ingest_router)
    application.include_router(discovery_runs_router)
    application.include_router(pii_flags_router)
    application.include_router(pii_decisions_router)
    application.include_router(pii_scan_router)

    @application.on_event("startup")
    def on_startup():
        """Log startup — schema migrations are handled by Alembic in start.sh."""
        logger.info("AICRM backend started (version=%s)", APP_VERSION)

    @application.get("/")
    def root():
        return {"message": f"{APP_NAME} backend is running"}

    return application


# Module-level app for normal uvicorn startup
app = create_app()
