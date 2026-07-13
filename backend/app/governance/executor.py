"""RTBF erasure executor (governance #76).

Drives a verified deletion request through the ONE sanctioned physical DELETE in the product:
claim (verifying -> executing, atomic, status-guarded), then a single transaction that
(1) deletes the subject's op-log row, (2) NULLs the dataset's profile values — the subject's
PII can sit in ANY profiled column, so surgical matching would under-delete, (3) inserts the
suppression entry so re-ingest cannot resurrect the subject, (4) writes the proof-of-erasure
audit row ON THE SAME CURSOR — erasure without proof is impossible by construction, and
(5) finalizes the request with counts and subject_key = NULL: the completed row plus the audit
row ARE the proof, without retaining the identifier.

The audit row stays inside the shipped CHECK enum: action='delete', entity_type='erasure',
detail carrying the counts and the key_hash (never the raw key).

Claim exclusivity uses `attempts` as a GENERATION TOKEN (the BEHAVIORAL-ARCHITECTURE §RTBF
verification-forced guard): the claim returns the generation it claimed, and finalize and
failure-reset are fenced with `AND attempts = <generation>` — a woken zombie whose row was
reaped and re-claimed can no longer stomp the live claim's state or burn its attempts.

Failure is retry-not-fail (#76: no 'failed' state — erasure is pure in-DB and idempotent):
any error rolls the erasure transaction back whole and resets executing -> verifying with
attempts+1 and error_detail. execute_deletion returns False rather than raising; if even the
reset fails, the reaper is the designed backstop for orphaned 'executing' rows.

Recorded limitations (product-level, not this module's): profiles whose discovered_field lost
its dataset (FK ON DELETE SET NULL) are unscopable and escape the wipe — datasets soft-delete
in this product, so the path is cold; subject_key matching is exact-byte against the op-log
(the /verify endpoint owns input hygiene).
"""

import contextlib
from datetime import datetime, timezone
from uuid import uuid4

from app.audit.recorder import record_audit
from app.db.connection import get_cursor
from app.governance.hashing import subject_key_hash

_KEY_MAX = 255  # mirrors app/ingest/mapper business_key cap


def claim_for_execution(request_id: str) -> int | None:
    """Atomically flip verifying -> executing. Returns the claimed GENERATION (the row's
    attempts value) or None when the row is in the wrong state / already claimed."""
    with get_cursor() as cur:
        cur.execute(
            "UPDATE deletion_requests SET status = 'executing', updated_at = NOW() "
            "WHERE id = %s AND status = 'verifying' "
            "RETURNING COALESCE(attempts, 0) AS attempts",
            (request_id,),
        )
        row = cur.fetchone()
        return row["attempts"] if row else None


def _reset_to_verifying(request_id: str, generation: int, exc: Exception) -> None:
    """Retry-not-fail: requeue with the cause recorded — fenced to OUR generation, so a
    zombie's late failure can never knock back a newer claim."""
    with get_cursor() as cur:
        cur.execute(
            "UPDATE deletion_requests SET status = 'verifying', "
            "attempts = COALESCE(attempts, 0) + 1, error_detail = %s, updated_at = NOW() "
            "WHERE id = %s AND status = 'executing' AND COALESCE(attempts, 0) = %s",
            (str(exc)[:255], request_id, generation),
        )


def execute_deletion(
    request_id: str, claimed: bool = False, generation: int | None = None
) -> bool:
    """Erase, suppress, audit, finalize — all-or-nothing. True when the request completed.

    claimed=True means the caller already owns the executing state (the worker's SKIP LOCKED
    claim) and MUST pass the generation its claim returned; claimed=False claims here (the
    inline /verify path). Returns False on any failure — never raises for runtime causes.
    """
    if claimed and generation is None:
        raise TypeError("claimed=True requires the generation returned by the claim")
    try:
        if not claimed:
            generation = claim_for_execution(request_id)
            if generation is None:
                return False
        with get_cursor() as cur:
            cur.execute(
                "SELECT dataset_id, subject_key, verified_by FROM deletion_requests "
                "WHERE id = %s AND status = 'executing' AND COALESCE(attempts, 0) = %s",
                (request_id, generation),
            )
            row = cur.fetchone()
            if row is None:
                return False  # reaped/re-claimed or externally finalized — not ours anymore
            dataset_id, subject_key = row["dataset_id"], row["subject_key"]
            if not dataset_id or subject_key is None:
                raise RuntimeError(
                    "deletion request is missing dataset_id or subject_key — cannot erase"
                )
            business_key = subject_key[:_KEY_MAX]
            key_hash = subject_key_hash(dataset_id, business_key)

            cur.execute(
                "DELETE FROM ingested_records WHERE dataset_id = %s AND business_key = %s",
                (dataset_id, business_key),
            )
            records_deleted = cur.rowcount

            cur.execute(
                "UPDATE field_profiles SET min_value = NULL, max_value = NULL, "
                "most_common_value = NULL, updated_at = NOW() "
                "WHERE discovered_field_id IN "
                "(SELECT id FROM discovered_fields WHERE dataset_id = %s)",
                (dataset_id,),
            )
            profiles_cleared = cur.rowcount

            cur.execute(
                "INSERT INTO suppression_entries "
                "(id, name, key_hash, dataset_id, deletion_request_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (key_hash) DO NOTHING",
                (
                    uuid4().hex,
                    f"suppression {key_hash[:16]}",
                    key_hash,
                    dataset_id,
                    request_id,
                ),
            )

            record_audit(
                cur,
                row["verified_by"] or "system",
                "delete",
                "erasure",
                request_id,
                detail=(
                    f"records_deleted={records_deleted} "
                    f"profiles_cleared={profiles_cleared} key_hash={key_hash}"
                ),
            )

            completed_at = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "UPDATE deletion_requests SET status = 'completed', records_deleted = %s, "
                "profiles_cleared = %s, completed_at = %s, subject_key = NULL, "
                "updated_at = NOW() "
                "WHERE id = %s AND status = 'executing' AND COALESCE(attempts, 0) = %s",
                (
                    records_deleted,
                    profiles_cleared,
                    completed_at,
                    request_id,
                    generation,
                ),
            )
            if cur.rowcount == 0:
                raise RuntimeError(
                    "claim lost mid-erasure (reaped or re-claimed) — aborting the transaction"
                )
        return True
    except Exception as exc:  # noqa: BLE001 — retry-not-fail: record and requeue
        if generation is not None:
            with contextlib.suppress(
                Exception
            ):  # reset failing too: reaper is the backstop
                _reset_to_verifying(request_id, generation, exc)
        return False
