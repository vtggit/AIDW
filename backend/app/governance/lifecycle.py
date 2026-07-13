"""Deletion-request lifecycle transitions (RTBF #76): verify and reject.

verify = the off-system identity check happened: received -> verifying (verified-and-queued,
THE claimable state), recording who/when and computing the subject_key_hash. In inline
executor mode the erasure then runs synchronously — erasure needs no egress, so it never
gates on ENABLE_INAPI_EGRESS.

reject is valid from received/verifying only. Both transitions are status-guarded (a lost
race raises WrongState — terminal states win) and write their audit row on the SAME cursor
as the transition, so a transition and its audit commit or roll back together.
"""

from datetime import datetime, timezone

from app import config
from app.audit.recorder import record_audit
from app.db.connection import get_cursor
from app.governance.executor import execute_deletion
from app.governance.hashing import subject_key_hash

_KEY_MAX = 255


class WrongState(Exception):
    """The transition's from-state no longer holds, or required fields are missing."""


def verify_request(request_id: str, actor: str) -> bool:
    """received -> verifying. Returns False when the request does not exist; raises
    WrongState on a state/field conflict. Inline mode then executes synchronously."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT dataset_id, subject_key, status FROM deletion_requests WHERE id = %s",
            (request_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        if row["status"] != "received":
            raise WrongState(
                f"verify requires status 'received', not {row['status']!r}"
            )
        if not row["dataset_id"] or row["subject_key"] is None:
            raise WrongState(
                "verify requires dataset_id and subject_key on the request"
            )
        key_hash = subject_key_hash(row["dataset_id"], row["subject_key"][:_KEY_MAX])
        verified_at = datetime.now(timezone.utc).isoformat()
        cur.execute(
            "UPDATE deletion_requests SET status = 'verifying', verified_by = %s, "
            "verified_at = %s, subject_key_hash = %s, updated_at = NOW() "
            "WHERE id = %s AND status = 'received'",
            (actor, verified_at, key_hash, request_id),
        )
        if cur.rowcount == 0:  # raced: rolls the whole transition back
            raise WrongState("verify lost the race — the request left 'received'")
        record_audit(
            cur,
            actor,
            "update",
            "deletion_requests",
            request_id,
            detail="verify: received -> verifying",
        )
    if config.INGEST_EXECUTOR == "inline":
        execute_deletion(
            request_id
        )  # claims verifying -> executing itself; retry-not-fail
    return True


def reject_request(request_id: str, actor: str) -> bool:
    """received|verifying -> rejected. Returns False when the request does not exist."""
    with get_cursor() as cur:
        cur.execute("SELECT status FROM deletion_requests WHERE id = %s", (request_id,))
        row = cur.fetchone()
        if row is None:
            return False
        if row["status"] not in ("received", "verifying"):
            raise WrongState(
                f"reject requires received/verifying, not {row['status']!r}"
            )
        cur.execute(
            "UPDATE deletion_requests SET status = 'rejected', updated_at = NOW() "
            "WHERE id = %s AND status IN ('received', 'verifying')",
            (request_id,),
        )
        if cur.rowcount == 0:
            raise WrongState("reject lost the race — the request changed state")
        record_audit(
            cur,
            actor,
            "update",
            "deletion_requests",
            request_id,
            detail=f"reject: {row['status']} -> rejected",
        )
    return True
