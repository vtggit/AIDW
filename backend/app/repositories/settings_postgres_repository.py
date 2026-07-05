"""PostgreSQL-backed repository for Settings."""

import json
import logging
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.observability.logging import get_request_id
from app.repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)

_SETTINGS_ID = "app"


def _req() -> str:
    """Return a request-ID suffix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


def _row_to_dict(row) -> dict:
    """Convert a DB row into a plain dict with ISO timestamps."""
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key):
            ts = d[key]
            if isinstance(ts, datetime):
                d[key] = ts.isoformat()
    # Ensure payload is a plain dict (psycopg2 may return dict already)
    if isinstance(d.get("payload"), str):
        d["payload"] = json.loads(d["payload"])
    return d


class SettingsPostgresRepository(SettingsRepository):
    """PostgreSQL-backed repository for the single settings record."""

    def get_settings(self) -> dict | None:
        """Return the current settings record, or a default if not yet created."""
        try:
            with get_cursor() as cur:
                cur.execute("SELECT * FROM settings WHERE id = %s", (_SETTINGS_ID,))
                row = cur.fetchone()
        except Exception as exc:
            logger.error("settings: failed to read settings — %s%s", exc, _req())
            raise

        if row is None:
            # Seed a default empty settings record
            return self._seed_default()

        return _row_to_dict(row)

    def update_settings(self, payload: dict) -> dict | None:
        """Merge *payload* into the existing settings record.

        Creates the record if it does not yet exist.
        """
        now = datetime.now(timezone.utc)

        try:
            with get_cursor() as cur:
                # Upsert: merge payload into existing JSONB or create new row
                cur.execute(
                    """INSERT INTO settings (id, payload, created_at, updated_at)
                       VALUES (%s, %s::jsonb, %s, %s)
                       ON CONFLICT (id) DO UPDATE
                       SET payload = settings.payload || %s::jsonb,
                           updated_at = %s
                       RETURNING *""",
                    (
                        _SETTINGS_ID,
                        json.dumps(payload),
                        now,
                        now,
                        json.dumps(payload),
                        now,
                    ),
                )
                row = cur.fetchone()
        except Exception as exc:
            logger.error(
                "settings: failed to update settings — %s%s",
                exc,
                _req(),
            )
            raise

        return _row_to_dict(row) if row else None

    def _seed_default(self) -> dict:
        """Create a default empty settings record."""
        now = datetime.now(timezone.utc)
        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO settings (id, payload, created_at, updated_at)
                       VALUES (%s, %s::jsonb, %s, %s)""",
                    (_SETTINGS_ID, json.dumps({}), now, now),
                )
        except Exception as exc:
            logger.error(
                "settings: failed to seed default settings — %s%s",
                exc,
                _req(),
            )
            raise
        return {
            "id": _SETTINGS_ID,
            "payload": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
