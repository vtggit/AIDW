"""Data-profiling endpoint: POST /api/sources/{source_id}/profile.

Fetches a sampled data page per dataset (interim in-API egress), writes field_profiles, and
re-scores the source's suggestions with real cardinality/fill. Gated by ENABLE_INAPI_EGRESS
(default off) like discovery; admin-only.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.config import ENABLE_INAPI_EGRESS
from app.profiling.service import ProfilingError, profile_source

router = APIRouter(prefix="/api/sources", tags=["profiling"])


@router.post("/{source_id}/profile", status_code=status.HTTP_200_OK)
def profile(source_id: str, _user=Depends(require_role(ROLE_ADMIN))):
    if not ENABLE_INAPI_EGRESS:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "in-API profiling is disabled (set ENABLE_INAPI_EGRESS=true to enable the interim "
            "in-API egress path)",
        )
    try:
        return profile_source(source_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    except ProfilingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
