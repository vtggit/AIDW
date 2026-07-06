"""Schema-discovery endpoint: POST /api/sources/{source_id}/discover.

Runs the deterministic reader for the source's connector type and upserts datasets/discovered_
fields. Gated by ENABLE_INAPI_EGRESS (default off) — the interim in-API egress path used before
the dedicated connector worker exists; admin-only, like other mutating endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.config import ENABLE_INAPI_EGRESS
from app.discovery.service import DiscoveryError, discover_source

router = APIRouter(prefix="/api/sources", tags=["discovery"])


@router.post("/{source_id}/discover", status_code=status.HTTP_200_OK)
def discover(source_id: str, _user=Depends(require_role(ROLE_ADMIN))):
    if not ENABLE_INAPI_EGRESS:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "in-API discovery is disabled (set ENABLE_INAPI_EGRESS=true to enable the interim "
            "in-API egress path)",
        )
    try:
        return discover_source(source_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    except DiscoveryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
