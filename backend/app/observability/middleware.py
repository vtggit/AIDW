"""Request ID and request logging middleware for AICRM backend.

Every incoming request gets a unique correlation ID that is:
    - Propagated from the ``X-Request-ID`` header if present
    - Otherwise generated as a short UUID
    - Attached to the response via the ``X-Request-ID`` header
    - Available to all log lines through the logging context

In addition, a single summary log line is emitted per request so you can
answer: what request came in, what request ID it had, and whether it
succeeded or failed.

This makes it trivial to grep all log lines belonging to a single request.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp

from app.observability.logging import clear_request_id, set_request_id

# Header name used for request correlation
REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a request ID to every request and expose it in logs + response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # Propagate or generate a request ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or _generate_request_id()
        set_request_id(request_id)

        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            clear_request_id()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log a summary line for every request after it completes.

    Each request produces one ``INFO`` log line containing the HTTP method,
    path, response status code, and duration in milliseconds.  Unhandled
    exceptions produce an ``ERROR`` log line instead.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Silence the default uvicorn access log to avoid duplication
        # when running under uvicorn; keep our structured line instead.
        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_access.setLevel(logging.WARNING)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "request failed method=%s path=%s status=500 duration_ms=%s error=%s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request completed method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


def _generate_request_id() -> str:
    """Generate a short, URL-safe request ID."""
    return str(uuid.uuid4())
