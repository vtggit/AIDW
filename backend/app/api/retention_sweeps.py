"""Retention sweep execution route (governance #80).

POST /api/retention-policies/{policy_id}/sweep — enqueue + execute one sweep run for the policy
(synchronous v1, matching /test /discover /profile: worker-claimed execution arrives when those
migrate). The response is the finished retention_runs row — the audit spine record — whether the
sweep succeeded or failed."""

from fastapi import APIRouter, Depends, HTTPException

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.retention.service import SweepError, create_pending_sweep, execute_sweep

router = APIRouter(prefix="/api/retention-policies", tags=["retention-sweeps"])


@router.post("/{policy_id}/sweep")
def sweep_policy(
    policy_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Run one retention sweep for the policy now. Destructive by design (purge policies DELETE
    below the cutoff) — admin only."""
    try:
        run = create_pending_sweep(policy_id, trigger="manual")
    except SweepError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finished = execute_sweep(run["id"])
    if finished is None:  # claimed by a concurrent executor between enqueue and execute
        raise HTTPException(status_code=409, detail="run %s already claimed" % run["id"])
    return finished
