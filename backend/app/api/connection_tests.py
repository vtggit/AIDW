"""ConnectionTest API routes."""

import base64
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.db.connection import get_cursor
from app.models.connection_tests import (
    ConnectionTestCreate,
    ConnectionTestResponse,
    ConnectionTestUpdate,
)
from app.repositories.connection_tests_postgres_repository import (
    ConnectionTestPostgresRepository,
)
from app.services.connection_tests_service import ConnectionTestService

router = APIRouter(prefix="/api/connection-tests", tags=["connection-tests"])

_repository = ConnectionTestPostgresRepository()
_service = ConnectionTestService(repository=_repository)


def get_service() -> ConnectionTestService:
    return _service


class EgressAuthError(Exception):
    """Raised when the source rejects the supplied credentials (HTTP 401/403)."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_metadata_url(entity_id: str) -> str | None:
    """Join the source connection endpoint with the OData metadata path.

    Returns None when the test's source has no connection endpoint configured.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT ct.source_id, sc.endpoint, osc.metadata_path "
            "FROM connection_tests ct "
            "LEFT JOIN source_connections sc ON sc.source_id = ct.source_id "
            "LEFT JOIN odata_service_configs osc ON osc.source_id = ct.source_id "
            "WHERE ct.id = %s",
            (entity_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    endpoint = (row.get("endpoint") or "").strip().rstrip("/")
    if not endpoint:
        return None
    metadata_path = (row.get("metadata_path") or "").strip() or "$metadata"
    if not metadata_path.startswith("/"):
        metadata_path = "/" + metadata_path
    return f"{endpoint}{metadata_path}"


def _resolve_auth_header(entity_id: str) -> str | None:
    """Build an Authorization header from the source's credential, if any.

    Reads the secret from the environment variable named by the credential's
    secret_ref at call time. Returns None when no credential or no secret is
    available.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT sc.auth_scheme, sc.principal, sc.secret_ref "
            "FROM source_credentials sc "
            "JOIN connection_tests ct ON ct.source_id = sc.source_id "
            "WHERE ct.id = %s",
            (entity_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    secret_ref = (row.get("secret_ref") or "").strip()
    if not secret_ref:
        return None
    secret = os.environ.get(secret_ref)
    if not secret:
        return None
    scheme = (row.get("auth_scheme") or "").strip().lower()
    principal = (row.get("principal") or "").strip()
    if scheme == "basic":
        token = base64.b64encode(f"{principal}:{secret}".encode()).decode("ascii")
        return f"Basic {token}"
    return f"Bearer {secret}"


def _fetch_metadata(url: str, auth_header: str | None) -> int:
    """Perform an authenticated GET of the metadata URL.

    Returns the HTTP status code on success. Raises EgressAuthError on 401/403
    and urllib.error.HTTPError (or any other exception) otherwise.
    """
    request = urllib.request.Request(url, method="GET")
    if auth_header:
        request.add_header("Authorization", auth_header)
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        return int(response.status)


def _run_connection_test(entity_id: str) -> ConnectionTestResponse:
    """Execute the connection test and persist the outcome."""
    url = _resolve_metadata_url(entity_id)
    auth_header = _resolve_auth_header(entity_id)

    status_value = "unreachable"
    message = "Connection test could not reach the source metadata endpoint."
    latency_ms: int | None = None

    if url is not None:
        started = time.monotonic()
        try:
            http_status = _fetch_metadata(url, auth_header)
            latency_ms = int((time.monotonic() - started) * 1000)
            if 200 <= http_status < 300:
                status_value = "ok"
                message = f"Source metadata endpoint responded with HTTP {http_status}."
            else:
                status_value = "unreachable"
                message = f"Source metadata endpoint responded with HTTP {http_status}."
        except EgressAuthError:
            latency_ms = int((time.monotonic() - started) * 1000)
            status_value = "auth_failed"
            message = "Source rejected the supplied credentials."
        except urllib.error.HTTPError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            if exc.code in (401, 403):
                status_value = "auth_failed"
                message = "Source rejected the supplied credentials."
            else:
                status_value = "unreachable"
                message = f"Source metadata endpoint responded with HTTP {exc.code}."
        except Exception:
            latency_ms = int((time.monotonic() - started) * 1000)
            status_value = "unreachable"
            message = "Connection test could not reach the source metadata endpoint."

    tested_at = _utc_now_iso()

    with get_cursor() as cur:
        cur.execute(
            "UPDATE connection_tests "
            "SET status = %s, message = %s, latency_ms = %s, tested_at = %s, updated_at = %s "
            "WHERE id = %s",
            (status_value, message, latency_ms, tested_at, tested_at, entity_id),
        )

    entity = _service.get_connection_test(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return entity


@router.get("", response_model=list[ConnectionTestResponse])
def list_connection_tests(
    _user: AuthUser = Depends(require_authenticated_user),
    service: ConnectionTestService = Depends(get_service),
):
    return service.list_connection_tests()


@router.post(
    "", response_model=ConnectionTestResponse, status_code=status.HTTP_201_CREATED
)
def create_connection_test(
    payload: ConnectionTestCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ConnectionTestService = Depends(get_service),
):
    return service.create_connection_test(payload)


@router.post("/{entity_id}/run", response_model=ConnectionTestResponse)
def run_connection_test(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Execute a live connection test against the source metadata endpoint."""
    existing = _service.get_connection_test(entity_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return _run_connection_test(entity_id)


@router.get("/{entity_id}", response_model=ConnectionTestResponse)
def get_connection_test(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: ConnectionTestService = Depends(get_service),
):
    entity = service.get_connection_test(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=ConnectionTestResponse)
def update_connection_test(
    entity_id: str,
    payload: ConnectionTestUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ConnectionTestService = Depends(get_service),
):
    entity = service.update_connection_test(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection_test(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: ConnectionTestService = Depends(get_service),
):
    if not service.delete_connection_test(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
