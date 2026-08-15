"""ConnectionTest API routes."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

import app.egress.http as egress_http
from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.db.connection import get_cursor
from app.egress.http import EgressAuthError
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
    service: ConnectionTestService = Depends(get_service),
):
    """Execute a live connectivity check against the test's source metadata URL.

    The fetch is delegated to the egress subsystem (``app.egress.http.fetch_bytes``),
    which resolves the applicable stored credential and applies its authorization.
    This module performs no credential handling of its own.
    """
    entity = service.get_connection_test(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )

    source_id = entity.get("source_id")
    if source_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ConnectionTest '{entity_id}' has no source to test.",
        )

    with get_cursor() as cur:
        cur.execute(
            "SELECT endpoint FROM source_connections WHERE source_id = %s "
            "ORDER BY created_at LIMIT 1",
            (source_id,),
        )
        connection_row = cur.fetchone()
        cur.execute(
            "SELECT metadata_path FROM odata_service_configs WHERE source_id = %s "
            "ORDER BY created_at LIMIT 1",
            (source_id,),
        )
        config_row = cur.fetchone()

    if connection_row is None or not connection_row.get("endpoint"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ConnectionTest '{entity_id}' has no source connection endpoint.",
        )

    endpoint = str(connection_row["endpoint"]).rstrip("/")
    metadata_path = (config_row or {}).get("metadata_path") or "$metadata"
    metadata_path = str(metadata_path).lstrip("/")
    metadata_url = f"{endpoint}/{metadata_path}"

    started = time.monotonic()
    try:
        egress_http.fetch_bytes(metadata_url)
        result_status = "ok"
        message = "Connection test succeeded."
    except EgressAuthError:
        result_status = "auth_failed"
        message = "Authentication failed against the source endpoint."
    except Exception:
        result_status = "unreachable"
        message = "Source endpoint is unreachable."
    latency_ms = int((time.monotonic() - started) * 1000)
    tested_at = datetime.now(timezone.utc).isoformat()

    with get_cursor() as cur:
        cur.execute(
            "UPDATE connection_tests "
            "SET status = %s, message = %s, latency_ms = %s, tested_at = %s, "
            "updated_at = %s WHERE id = %s",
            (result_status, message, latency_ms, tested_at, tested_at, entity_id),
        )

    updated = service.get_connection_test(entity_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConnectionTest '{entity_id}' not found.",
        )
    return updated


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
