"""Steward decision endpoints for PII flags (governance #75).

POST /api/pii-flags/{id}/confirm  — mark a flag as real PII (sticky, profile stays suppressed)
POST /api/pii-flags/{id}/dismiss  — mark a false positive (sticky, suppression lifts next profile)
POST /api/sources/{id}/pii-scan   — manual/backfill schema-tier scan of a source

Admin-only. confirm/dismiss write the audit trail atomically with the status change (Option B —
an audit failure rolls the mutation back), making these the audit table's first real writers.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.pii.service import confirm_flag, dismiss_flag, scan_pii_for_source

flags_router = APIRouter(prefix="/api/pii-flags", tags=["pii"])
scan_router = APIRouter(prefix="/api/sources", tags=["pii"])


@flags_router.post("/{flag_id}/confirm")
def confirm(flag_id: str, user: AuthUser = Depends(require_role(ROLE_ADMIN))):
    try:
        return confirm_flag(flag_id, user.sub)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pii_flag not found")


@flags_router.post("/{flag_id}/dismiss")
def dismiss(flag_id: str, user: AuthUser = Depends(require_role(ROLE_ADMIN))):
    try:
        return dismiss_flag(flag_id, user.sub)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pii_flag not found")


@scan_router.post("/{source_id}/pii-scan", status_code=status.HTTP_200_OK)
def pii_scan(source_id: str, _user: AuthUser = Depends(require_role(ROLE_ADMIN))):
    """Manual/backfill schema-tier PII scan. No egress (reads only the persisted schema), so it
    is not gated by ENABLE_INAPI_EGRESS."""
    return scan_pii_for_source(source_id)
