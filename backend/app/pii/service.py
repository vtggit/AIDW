"""Persist + reconcile PII flags for a source, with retro-scrub of leaked profile values.

Governance #75, the module that WRITES ``pii_flags`` and closes the live PII-at-rest leak.
Mirrors the suggestion reconciler (``app/suggestion/service.py``): idempotent, bidirectional,
never deletes, human decisions sticky. Two governance-specific behaviors on top:

* **Retro-scrub (closes the leak).** When a field carries an ACTIVE flag (``flagged`` or
  human-``confirmed``), any existing ``field_profiles`` row for it has its raw example values
  (``min_value`` / ``max_value`` / ``most_common_value``) NULLed in the SAME transaction — so
  data profiled BEFORE the watchdog flagged the field stops leaking values at rest. Aggregate
  counts (row/null/distinct) are statistics, not values, and are kept. Each scrub writes an
  ``audit_log`` row (``action='redact_profile'``, actor ``system:pii-watchdog``, NO raw values
  in details) on the same cursor, so scrub and evidence commit atomically.

* **Tier-aware staling (the ratchet).** A schema-tier scan reads only names; it therefore stales
  only schema-tier flags whose name rule stopped firing. A profile-tier flag is NEVER staled by
  a schema scan (a pass without the field's sampled values proves nothing — only a human dismiss
  releases it). A vanished field (its ``discovered_field_id`` gone from the live set) stales its
  flags regardless of tier.

``(dataset_id, fingerprint)`` is the semantic identity (``fingerprint = sha256(name|category)``),
so a profile-tier detection upgrades the SAME flag a schema-tier detection created rather than
duplicating it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.pii.engine import detect_pii_candidates

logger = logging.getLogger(__name__)

DETECTION_TIER_SCHEMA = "schema"
_AUDIT_ACTOR = "system:pii-watchdog"


def _scrub_profile(cur, discovered_field_id, now) -> bool:
    """NULL the raw example values on the field's profile row, keeping aggregate counts. Guarded
    on 'has any value' so it is idempotent (a second call is a no-op) and only reports a scrub
    when it actually removed leaked data. Returns whether a row was scrubbed."""
    if not discovered_field_id:
        return False
    cur.execute(
        "UPDATE field_profiles SET min_value = NULL, max_value = NULL, "
        "most_common_value = NULL, updated_at = %s "
        "WHERE discovered_field_id = %s AND (min_value IS NOT NULL "
        "OR max_value IS NOT NULL OR most_common_value IS NOT NULL)",
        (now, discovered_field_id),
    )
    return cur.rowcount > 0


def _audit_scrub(cur, discovered_field_id, dataset_id, now) -> None:
    """Record the redaction on the SAME cursor (scrub + evidence are one transaction). details
    carry ids only — never the values that were removed (that would re-retain what we scrubbed).
    """
    cur.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, actor_sub, timestamp, "
        "details_json) VALUES (%s, %s, %s, %s, %s, %s)",
        (
            "pii_flag",
            discovered_field_id,
            "redact_profile",
            _AUDIT_ACTOR,
            now,
            json.dumps({"dataset_id": dataset_id, "reason": "active_pii_flag"}),
        ),
    )


def _scrub_and_audit(cur, field_id, dataset_id, now) -> int:
    if _scrub_profile(cur, field_id, now):
        _audit_scrub(cur, field_id, dataset_id, now)
        return 1
    return 0


def reconcile_flags_for_dataset(
    cur, dataset_id, field_rows, candidates, scan_tier, now=None
) -> dict:
    """Reconcile one tier's PII candidates into ``pii_flags`` for a dataset, on an open cursor.

    ``field_rows`` are the dataset's current ``discovered_fields`` (need ``id`` + ``name`` so a
    candidate binds to the real field). ``scan_tier`` (``schema`` | ``profile``) is which tier's
    fresh set this call carries — the stale-pass only stales flags of that tier (the ratchet).
    Returns per-dataset counts.
    """
    now = now or datetime.now(timezone.utc)
    name_to_field_id = {r["name"]: r["id"] for r in field_rows}
    live_field_ids = set(name_to_field_id.values())
    fresh = {c["fingerprint"]: c for c in candidates}

    cur.execute(
        "SELECT id, fingerprint, status, detection_tier, discovered_field_id "
        "FROM pii_flags WHERE dataset_id = %s",
        (dataset_id,),
    )
    existing = {
        row["fingerprint"]: dict(row)
        for row in cur.fetchall()
        if row["fingerprint"] is not None
    }

    created = revived = upgraded = staled = 0

    for fp, cand in fresh.items():
        field_id = name_to_field_id.get(cand["field_name"])
        ex = existing.get(fp)

        if ex is None:
            cur.execute(
                "INSERT INTO pii_flags (id, name, dataset_id, discovered_field_id, category, "
                "detection_tier, status, confidence, rationale, fingerprint, created_at, "
                "updated_at) VALUES (%s, %s, %s, %s, %s, %s, 'flagged', %s, %s, %s, %s, %s)",
                (
                    str(uuid4()),
                    f"{cand['category']}:{cand['field_name']}"[:255],
                    dataset_id,
                    field_id,
                    cand["category"],
                    cand["detection_tier"],
                    cand["confidence"],
                    cand["rationale"],
                    fp,
                    now,
                    now,
                ),
            )
            created += 1
            continue

        status = ex["status"]
        if status in ("dismissed", "confirmed"):
            # sticky human decisions — never re-flag/resurrect; scrub (for 'confirmed') is
            # handled by the active-flag sweep below, so 'dismissed' is never scrubbed
            continue
        if status == "stale":
            cur.execute(
                "UPDATE pii_flags SET status = 'flagged', detection_tier = %s, confidence = %s, "
                "rationale = %s, discovered_field_id = %s, updated_at = %s WHERE id = %s",
                (
                    cand["detection_tier"],
                    cand["confidence"],
                    cand["rationale"],
                    field_id,
                    now,
                    ex["id"],
                ),
            )
            revived += 1
        elif (
            ex["detection_tier"] == DETECTION_TIER_SCHEMA
            and cand["detection_tier"] != DETECTION_TIER_SCHEMA
        ):
            # a profile-tier detection confirms a schema-tier flag: upgrade tier + confidence
            cur.execute(
                "UPDATE pii_flags SET detection_tier = %s, confidence = %s, rationale = %s, "
                "discovered_field_id = %s, updated_at = %s WHERE id = %s",
                (
                    cand["detection_tier"],
                    cand["confidence"],
                    cand["rationale"],
                    field_id,
                    now,
                    ex["id"],
                ),
            )
            upgraded += 1
        elif field_id is not None and ex["discovered_field_id"] != field_id:
            # same rule, but the field was re-created under a new id — rebind
            cur.execute(
                "UPDATE pii_flags SET discovered_field_id = %s, updated_at = %s WHERE id = %s",
                (field_id, now, ex["id"]),
            )

    for fp, ex in existing.items():
        if fp in fresh or ex["status"] != "flagged":
            continue
        field_gone = ex["discovered_field_id"] not in live_field_ids
        if ex["detection_tier"] == scan_tier or field_gone:
            cur.execute(
                "UPDATE pii_flags SET status = 'stale', updated_at = %s WHERE id = %s",
                (now, ex["id"]),
            )
            staled += 1

    # retro-scrub sweep: every field that ends this run with an ACTIVE flag (flagged|confirmed)
    # has its leaked profile values scrubbed — a property of BEING flagged, not of THIS scan
    # re-detecting it, so a profile-tier flag's values are scrubbed even during a schema scan.
    # DISTINCT so a field with two flags is scrubbed (and audited) once.
    scrubbed = 0
    cur.execute(
        "SELECT DISTINCT discovered_field_id FROM pii_flags WHERE dataset_id = %s "
        "AND status IN ('flagged', 'confirmed') AND discovered_field_id IS NOT NULL",
        (dataset_id,),
    )
    for row in cur.fetchall():
        scrubbed += _scrub_and_audit(cur, row["discovered_field_id"], dataset_id, now)

    return {
        "created": created,
        "revived": revived,
        "upgraded": upgraded,
        "staled": staled,
        "scrubbed": scrubbed,
    }


def _flag_response(cur, flag_id: str) -> dict:
    cur.execute("SELECT * FROM pii_flags WHERE id = %s", (flag_id,))
    row = cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


def _audit_decision(cur, flag_id, action, actor_sub, now) -> None:
    """Audit a steward decision on the SAME cursor as the status change (Option B: an audit
    failure rolls the whole mutation back, so no decision is ever unrecorded)."""
    cur.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, actor_sub, timestamp, "
        "details_json) VALUES (%s, %s, %s, %s, %s, %s)",
        ("pii_flag", flag_id, action, actor_sub, now, json.dumps({})),
    )


def _set_flag_status(
    flag_id: str, new_status: str, action: str, actor_sub: str
) -> dict:
    """Steward decision: set a flag's status and audit it atomically. Raises LookupError if the
    flag is missing. ``actor_sub`` is the authenticated user's subject."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE pii_flags SET status = %s, updated_at = %s WHERE id = %s",
            (new_status, now, flag_id),
        )
        if cur.rowcount == 0:
            raise LookupError("pii_flag not found")
        _audit_decision(cur, flag_id, action, actor_sub, now)
        return _flag_response(cur, flag_id)


def confirm_flag(flag_id: str, actor_sub: str) -> dict:
    """Steward confirms a flag IS PII: status='confirmed' (sticky — the reconciler never stales
    or resurrects it) + audit. Its profile stays suppressed permanently."""
    return _set_flag_status(flag_id, "confirmed", "confirm", actor_sub)


def dismiss_flag(flag_id: str, actor_sub: str) -> dict:
    """Steward dismisses a false positive: status='dismissed' (sticky) + audit. Suppression lifts
    at the next profile pass (the field no longer carries an active flag)."""
    return _set_flag_status(flag_id, "dismissed", "dismiss", actor_sub)


def scan_pii_for_source(source_id: str) -> dict:
    """Schema-tier PII scan across every dataset of a source: run the name rules, reconcile into
    ``pii_flags``, retro-scrub any leaked profile values. Its own transaction, so a discovery
    caller can invoke it after the discovery commit and treat any failure as non-fatal.
    """
    totals = {
        "pii_flags_created": 0,
        "pii_flags_revived": 0,
        "pii_flags_upgraded": 0,
        "pii_flags_staled": 0,
        "profiles_redacted": 0,
    }
    with get_cursor() as cur:
        cur.execute("SELECT id FROM datasets WHERE source_id = %s", (source_id,))
        dataset_ids = [r["id"] for r in cur.fetchall()]
        for ds_id in dataset_ids:
            cur.execute(
                "SELECT id, name, data_type, is_key FROM discovered_fields "
                "WHERE dataset_id = %s",
                (ds_id,),
            )
            field_rows = [dict(r) for r in cur.fetchall()]
            candidates = detect_pii_candidates(field_rows)
            counts = reconcile_flags_for_dataset(
                cur, ds_id, field_rows, candidates, DETECTION_TIER_SCHEMA
            )
            totals["pii_flags_created"] += counts["created"]
            totals["pii_flags_revived"] += counts["revived"]
            totals["pii_flags_upgraded"] += counts["upgraded"]
            totals["pii_flags_staled"] += counts["staled"]
            totals["profiles_redacted"] += counts["scrubbed"]
    return totals
