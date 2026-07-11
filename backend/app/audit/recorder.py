"""Same-transaction audit writes (governance #79).

record_audit writes one audit_logs row on the CALLER'S cursor: an audited write and its audit
row commit or roll back together, so the audit trail can never claim more or less than what
actually happened. Fail-closed on unknown actions BEFORE any write. This is the single helper
every mutating write-path calls — keep it dependency-free (no service imports) so any layer can
use it inside its own transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

_ACTIONS = ("create", "update", "delete")


def record_audit(
    cur,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: str | None = None,
) -> str:
    """INSERT one audit row using the caller's open cursor/transaction. Returns the row id.

    `action` must be one of create/update/delete (the audit_logs CHECK enum) — anything else
    raises ValueError before any write reaches the cursor.
    """
    if action not in _ACTIONS:
        raise ValueError(f"action {action!r} is not one of {_ACTIONS}")
    now = datetime.now(timezone.utc)
    audit_id = uuid.uuid4().hex
    cur.execute(
        "INSERT INTO audit_logs (id, name, actor, action, entity_type, entity_id, "
        "detail, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            audit_id,
            f"{action} {entity_type}",
            actor,
            action,
            entity_type,
            str(entity_id),
            detail,
            now,
            now,
        ),
    )
    return audit_id
