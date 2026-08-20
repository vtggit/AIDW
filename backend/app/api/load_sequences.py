"""LoadSequence API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.bpmn.ir import IRError
from app.db.connection import get_cursor
from app.models.load_sequences import (
    LoadSequenceCreate,
    LoadSequenceResponse,
    LoadSequenceUpdate,
)
from app.repositories.load_sequences_postgres_repository import (
    LoadSequencePostgresRepository,
)
from app.services.load_sequences_service import LoadSequenceService


class DueLoadSequenceResponse(BaseModel):
    id: str
    name: str
    schedule_cadence: str | None = None
    schedule_enabled: bool | None = None
    last_fired_at: str | None = None


router = APIRouter(prefix="/api/load-sequences", tags=["load-sequences"])

_repository = LoadSequencePostgresRepository()
_service = LoadSequenceService(repository=_repository)


def get_service() -> LoadSequenceService:
    return _service


@router.get("", response_model=list[LoadSequenceResponse])
def list_load_sequences(
    limit: int | None = Query(None, ge=1, le=100),
    offset: int | None = Query(None, ge=0),
    response: Response = None,
    _user: AuthUser = Depends(require_authenticated_user),
    service: LoadSequenceService = Depends(get_service),
):
    total = len(service.list_load_sequences())
    response.headers["X-Total-Count"] = str(total)
    return service.list_load_sequences(limit=limit, offset=offset)


@router.post(
    "", response_model=LoadSequenceResponse, status_code=status.HTTP_201_CREATED
)
def create_load_sequence(
    payload: LoadSequenceCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LoadSequenceService = Depends(get_service),
):
    return service.create_load_sequence(payload)


@router.get("/due", response_model=list[DueLoadSequenceResponse])
def get_due_load_sequences(
    not_fired_since: str = Query(..., description="ISO-8601 timestamp"),
    _user: AuthUser = Depends(require_authenticated_user),
):
    """Return load sequences that are due to fire.

    A sequence is considered due if:
    - schedule_cadence is set (not null)
    - schedule_enabled is not false
    - last_fired_at is null or older than not_fired_since
    """
    try:
        parsed = datetime.fromisoformat(not_fired_since)
        # If the parsed datetime has no timezone info, assume UTC.
        if parsed.tzinfo is None:
            threshold = parsed.replace(tzinfo=timezone.utc)
        else:
            threshold = parsed
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="not_fired_since must be a valid ISO-8601 timestamp.",
        )

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, schedule_cadence, schedule_enabled, last_fired_at
            FROM load_sequences
            WHERE schedule_cadence IS NOT NULL
              AND (schedule_enabled IS TRUE OR schedule_enabled IS NULL)
              AND (last_fired_at IS NULL OR last_fired_at <= %s)
            ORDER BY id
            """,
            (threshold,),
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        entry = {
            "id": row["id"],
            "name": row["name"],
            "schedule_cadence": row.get("schedule_cadence"),
            "schedule_enabled": row.get("schedule_enabled"),
            "last_fired_at": (
                row["last_fired_at"].isoformat()
                if row.get("last_fired_at") is not None
                else None
            ),
        }
        results.append(entry)

    return results


@router.get("/{entity_id}", response_model=LoadSequenceResponse)
def get_load_sequence(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: LoadSequenceService = Depends(get_service),
):
    entity = service.get_load_sequence(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=LoadSequenceResponse)
def update_load_sequence(
    entity_id: str,
    payload: LoadSequenceUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LoadSequenceService = Depends(get_service),
):
    entity = service.update_load_sequence(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_load_sequence(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: LoadSequenceService = Depends(get_service),
):
    if not service.delete_load_sequence(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{entity_id}' not found.",
        )


@router.get("/{sequence_id}/bpmn")
def generate_load_sequence_bpmn(
    sequence_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
):
    """Project a load sequence's ordered steps as a BPMN diagram.

    Returns the server-generated BPMN XML and SVG for the sequence's
    current step ordering.  Uses the same generation pipeline as
    process-definitions/generate (build_ir -> layout -> emit_bpmn / emit_svg).
    """
    from app.services.load_sequence_bpmn_service import project_load_sequence_to_bpmn

    try:
        result = project_load_sequence_to_bpmn(sequence_id)
    except IRError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot project sequence to BPMN: {exc}",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoadSequence '{sequence_id}' not found.",
        )
    return result
