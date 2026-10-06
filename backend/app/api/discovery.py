"""Schema-discovery endpoint: POST /api/sources/{source_id}/discover.

Runs the deterministic reader for the source's connector type and upserts datasets/discovered_
fields. An optional JSON body ``{"entity_sets": [...]}`` restricts the run to the named entity
sets; a name absent from the source's $metadata is a 422 naming every missing name. Gated by
ENABLE_INAPI_EGRESS (default off) — the interim in-API egress path used before the dedicated
connector worker exists; admin-only, like other mutating endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.authorization import ROLE_ADMIN, require_role
from app.config import ENABLE_INAPI_EGRESS
from app.discovery.service import DiscoveryError, discover_source

router = APIRouter(prefix="/api/sources", tags=["discovery"])


class DiscoverRequest(BaseModel):
    """Optional discovery body: ``entity_sets`` restricts the run to the named entity sets."""

    entity_sets: list[str] | None = None


@router.post("/{source_id}/discover", status_code=status.HTTP_200_OK)
def discover(
    source_id: str,
    payload: DiscoverRequest | None = None,
    _user=Depends(require_role(ROLE_ADMIN)),
):
    if not ENABLE_INAPI_EGRESS:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "in-API discovery is disabled (set ENABLE_INAPI_EGRESS=true to enable the interim "
            "in-API egress path)",
        )
    try:
        return discover_source(source_id, payload.entity_sets if payload else None)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except DiscoveryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
