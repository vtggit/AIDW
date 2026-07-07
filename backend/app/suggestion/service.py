"""Persist + reconcile schema-tier suggestions for a source.

Invoked automatically after a successful discovery run (the automatic trigger — suggestion no longer
hard-depends on ingest). Reconciliation, not blind insert, so it is idempotent and *bidirectional*:

* a candidate whose fingerprint is new  -> INSERT (with its role-tagged suggestion_fields);
* a candidate whose fingerprint already exists -> left as-is if the user has acted on it
  (accepted/dismissed are sticky and never resurrected), revived suggested if it was stale;
* an existing ``suggested``/``stale`` row the current schema no longer produces -> marked ``stale``.

So when a field vanishes upstream (or is retyped so a rule stops firing) the dependent suggestion
disappears from the default inbox instead of rotting — and reappears if the schema comes back. Never
deletes; user decisions are preserved.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.suggestion.engine import generate_suggestions

logger = logging.getLogger(__name__)


def _write_suggestion_fields(cur, suggestion_id, cand, name_to_field_id, now) -> None:
    """(Re)create a suggestion's role-tagged field bindings against the CURRENT discovered_field ids.
    Callers that rebind an existing suggestion must delete its old rows first."""
    for sf in cand.fields:
        cur.execute(
            "INSERT INTO suggestion_fields (id, name, suggestion_id, discovered_field_id, "
            "field_role, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                str(uuid4()),
                f"{sf.role}:{sf.field_name}",
                suggestion_id,
                name_to_field_id.get(sf.field_name),
                sf.role,
                now,
                now,
            ),
        )


def regenerate_for_dataset(
    cur, dataset_id: str, dataset_name: str, field_rows: list[dict]
) -> dict:
    """Reconcile one dataset's suggestions against the current schema, using an open cursor.

    ``field_rows`` are that dataset's ``discovered_fields`` rows (must include ``id`` + ``name`` so
    each candidate field binds to the real discovered_field). Returns per-dataset counts.
    """
    candidates = generate_suggestions(dataset_name, field_rows)
    name_to_field_id = {r["name"]: r["id"] for r in field_rows}
    fresh = {c.fingerprint: c for c in candidates}

    cur.execute(
        "SELECT id, fingerprint, status FROM suggestions WHERE dataset_id = %s",
        (dataset_id,),
    )
    existing = {
        row["fingerprint"]: (row["id"], row["status"])
        for row in cur.fetchall()
        if row["fingerprint"] is not None
    }

    now = datetime.now(timezone.utc)
    created = revived = staled = 0

    for fingerprint, cand in fresh.items():
        if fingerprint in existing:
            suggestion_id, status = existing[fingerprint]
            if status == "stale":
                # the schema produces it again — bring it back (it was never user-dismissed) and
                # rebind its fields: the old discovered_field_id was NULLed when the field vanished,
                # and the field has since returned under a NEW discovered_fields id.
                cur.execute(
                    "UPDATE suggestions SET status = 'suggested', score = %s, updated_at = %s "
                    "WHERE id = %s",
                    (cand.score, now, suggestion_id),
                )
                cur.execute(
                    "DELETE FROM suggestion_fields WHERE suggestion_id = %s",
                    (suggestion_id,),
                )
                _write_suggestion_fields(
                    cur, suggestion_id, cand, name_to_field_id, now
                )
                revived += 1
            # suggested/accepted/dismissed: leave untouched (anti-resurrection)
            continue

        suggestion_id = str(uuid4())
        cur.execute(
            "INSERT INTO suggestions (id, name, dataset_id, title, item_type, aggregation, "
            "score, rationale, strategy, status, fingerprint, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                suggestion_id,
                cand.title,
                dataset_id,
                cand.title,
                cand.item_type,
                cand.aggregation,
                cand.score,
                cand.rationale,
                cand.strategy,
                "suggested",
                fingerprint,
                now,
                now,
            ),
        )
        _write_suggestion_fields(cur, suggestion_id, cand, name_to_field_id, now)
        created += 1

    # stale-pass: an active (suggested) row the current schema no longer produces
    for fingerprint, (suggestion_id, status) in existing.items():
        if status == "suggested" and fingerprint not in fresh:
            cur.execute(
                "UPDATE suggestions SET status = 'stale', updated_at = %s WHERE id = %s",
                (now, suggestion_id),
            )
            staled += 1

    return {"created": created, "revived": revived, "staled": staled}


def regenerate_suggestions_for_source(source_id: str) -> dict:
    """Reconcile schema-tier suggestions across every dataset of a source. Its own transaction, so a
    discovery caller can invoke it after the discovery commit and treat any failure as non-fatal.
    """
    totals = {
        "suggestions_created": 0,
        "suggestions_revived": 0,
        "suggestions_staled": 0,
    }
    with get_cursor() as cur:
        cur.execute("SELECT id, name FROM datasets WHERE source_id = %s", (source_id,))
        datasets = cur.fetchall()
        for ds in datasets:
            cur.execute(
                "SELECT id, name, data_type, is_key, is_nullable, field_position "
                "FROM discovered_fields WHERE dataset_id = %s",
                (ds["id"],),
            )
            field_rows = [dict(r) for r in cur.fetchall()]
            counts = regenerate_for_dataset(cur, ds["id"], ds["name"], field_rows)
            totals["suggestions_created"] += counts["created"]
            totals["suggestions_revived"] += counts["revived"]
            totals["suggestions_staled"] += counts["staled"]
    return totals
