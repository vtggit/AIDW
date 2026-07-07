"""Accept / dismiss actions on suggestions.

Accept copies a suggestion 1:1 into a ``dashboard_item`` (title / item_type / aggregation), copies
its role-tagged ``suggestion_fields`` into ``dashboard_item_fields`` (so the item's axes/measures
are real discovered_field references), records ``source_suggestion_id`` for provenance, appends it
to a dashboard (an explicit one, else a get-or-created default), and marks the suggestion
``accepted``. Idempotent: a suggestion already accepted returns its existing item unchanged (the
UNIQUE index on source_suggestion_id is the DB-level backstop). Dismiss just marks the suggestion
``dismissed`` — the reconciler's anti-resurrection then keeps it from coming back.
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.repositories.dashboard_items_postgres_repository import (
    DashboardItemPostgresRepository,
)

DEFAULT_DASHBOARD_NAME = "Default Dashboard"


def _resolve_dashboard(cur, dashboard_id, now):
    """Return an existing dashboard id (verifying it exists) or get-or-create the default one."""
    if dashboard_id is not None:
        cur.execute("SELECT id FROM dashboards WHERE id = %s", (dashboard_id,))
        if cur.fetchone() is None:
            raise LookupError("dashboard not found")
        return dashboard_id

    cur.execute(
        "SELECT id FROM dashboards WHERE name = %s ORDER BY created_at LIMIT 1",
        (DEFAULT_DASHBOARD_NAME,),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    new_id = str(uuid4())
    cur.execute(
        "INSERT INTO dashboards (id, name, description, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            new_id,
            DEFAULT_DASHBOARD_NAME,
            "Auto-created for accepted suggestions.",
            now,
            now,
        ),
    )
    return new_id


def accept_suggestion(suggestion_id: str, dashboard_id: str | None = None) -> dict:
    """Accept a suggestion into a dashboard item. Raises LookupError if the suggestion (or an
    explicitly named dashboard) doesn't exist. Idempotent per suggestion."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM suggestions WHERE id = %s", (suggestion_id,))
        suggestion = cur.fetchone()
        if suggestion is None:
            raise LookupError("suggestion not found")

        # idempotent: already accepted into an item -> return that item, don't duplicate
        cur.execute(
            "SELECT id FROM dashboard_items WHERE source_suggestion_id = %s",
            (suggestion_id,),
        )
        existing = cur.fetchone()
        if existing:
            item_id = existing["id"]
        else:
            dash_id = _resolve_dashboard(cur, dashboard_id, now)
            cur.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next FROM dashboard_items "
                "WHERE dashboard_id = %s",
                (dash_id,),
            )
            position = cur.fetchone()["next"]

            item_id = str(uuid4())
            cur.execute(
                "INSERT INTO dashboard_items (id, name, dashboard_id, source_suggestion_id, "
                "title, item_type, aggregation, position, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    item_id,
                    suggestion.get("title") or suggestion.get("name"),
                    dash_id,
                    suggestion_id,
                    suggestion.get("title"),
                    suggestion.get("item_type"),
                    suggestion.get("aggregation"),
                    position,
                    now,
                    now,
                ),
            )
            cur.execute(
                "SELECT field_role, discovered_field_id FROM suggestion_fields "
                "WHERE suggestion_id = %s",
                (suggestion_id,),
            )
            for sf in cur.fetchall():
                cur.execute(
                    "INSERT INTO dashboard_item_fields (id, name, dashboard_item_id, "
                    "discovered_field_id, field_role, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        str(uuid4()),
                        f"{sf['field_role']}:{sf['discovered_field_id']}",
                        item_id,
                        sf["discovered_field_id"],
                        sf["field_role"],
                        now,
                        now,
                    ),
                )
            cur.execute(
                "UPDATE suggestions SET status = 'accepted', updated_at = %s WHERE id = %s",
                (now, suggestion_id),
            )

    return DashboardItemPostgresRepository().get_by_id(item_id)


def dismiss_suggestion(suggestion_id: str) -> dict:
    """Mark a suggestion dismissed (sticky — the reconciler never resurrects it). Raises LookupError
    if it doesn't exist. Returns the updated suggestion."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute("SELECT id FROM suggestions WHERE id = %s", (suggestion_id,))
        if cur.fetchone() is None:
            raise LookupError("suggestion not found")
        cur.execute(
            "UPDATE suggestions SET status = 'dismissed', updated_at = %s WHERE id = %s",
            (now, suggestion_id),
        )
        cur.execute("SELECT * FROM suggestions WHERE id = %s", (suggestion_id,))
        row = cur.fetchone()
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d
