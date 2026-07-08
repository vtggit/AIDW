"""Cursor-advance + run-count transaction over fetched rows.

Operates on an already-open database cursor so the caller composes it into ONE transaction with
the run/cursor bookkeeping (all-or-nothing per doc §5). The op-log write is an atomic
``INSERT ... ON CONFLICT (dataset_id, business_key) DO UPDATE`` — idempotent replay AND safe under
concurrent runs of the same pipeline (a plain SELECT-then-INSERT would race to a UniqueViolation).
Watermark advance is kind-aware (numeric/millisecond values compare as numbers, ISO-8601 and plain
strings as text), gated on candidacy (``_acceptable``: a value that cannot be ordered AND rendered
as a $filter literal for its kind never becomes the watermark — one bad remote row must not wedge
the pipeline), and page-cap-aware: a FULL page may have cut a tie group at its max value, so the
watermark only advances to the greatest value strictly BELOW the page max — the tie group is
refetched by the next strictly-greater filter instead of being lost. An entirely-tied full page
cannot advance at all (progress needs server paging inside the tie — Milestone 6 worker scope).
"""

import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

from app.ingest.mapper import business_key, normalize_cursor_value

logger = logging.getLogger(__name__)


def _later(candidate: str, current: str | None, cursor_kind: str | None) -> bool:
    """True when candidate is strictly later than the current watermark."""
    if current is None:
        return True
    if (cursor_kind or "").lower() in ("numeric", "timestamp"):
        try:
            return float(candidate) > float(current)
        except ValueError:
            pass  # ISO-8601 projections compare correctly as text
    return candidate > current


def _acceptable(value: str, cursor_kind: str | None) -> bool:
    """Only a value that is orderable AND renderable as a $filter literal for its kind may become
    a watermark candidate — a committed unrenderable watermark would wedge every future run of
    the pipeline (the poisoned-watermark failure mode)."""
    kind = (cursor_kind or "").lower()
    if kind == "numeric":
        try:
            # isfinite: json.loads parses bare Infinity/NaN, and float('inf'/'nan') succeeds —
            # but inf outranks every real value forever and nan breaks all comparisons
            return math.isfinite(float(value))
        except ValueError:
            return False
    if kind == "timestamp":
        if value.lstrip("-").isdigit():
            # digit strings are treated as V2 /Date(ms)/ counts; a compact digit date
            # ('20260707') is indistinguishable from a ms count here — it orders consistently
            # and renders a too-early (matches-everything) filter, never losing rows
            try:
                datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                return False  # a /Date(ms)/ count outside datetime range
            return True
        try:
            # a real ISO-8601 parse — first-character sniffing would let digit-leading junk
            # ('3-bad-data', '31/12/2026') outrank every ISO value in the text comparison
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    return True


def _advance(
    values: list[str], current: str | None, cursor_kind: str | None, page_full: bool
) -> str | None:
    """The new watermark after a page. On a full page the max value's tie group may be cut by the
    $top cap, so only values strictly below the page max are safe to advance to."""
    if not values:
        return current
    page_max = values[0]
    for v in values[1:]:
        if _later(v, page_max, cursor_kind):
            page_max = v
    if not page_full:
        return page_max if _later(page_max, current, cursor_kind) else current
    below = [v for v in values if _later(page_max, v, cursor_kind)]
    if not below:
        logger.warning(
            "full page entirely tied at cursor value %r — watermark cannot advance",
            page_max,
        )
        return current
    best = below[0]
    for v in below[1:]:
        if _later(v, best, cursor_kind):
            best = v
    return best if _later(best, current, cursor_kind) else current


def apply_rows(
    cur,
    run_id: str,
    dataset_id: str,
    rows: list[dict],
    key_fields: list[str],
    cursor_field: str | None = None,
    watermark: str | None = None,
    cursor_kind: str | None = None,
    now: datetime | None = None,
    page_full: bool = False,
) -> dict:
    """Upsert each row into the op-log and advance the watermark. Returns the observable counts:
    rows_read/rows_written/inserts/updates/skipped_no_key and the new_watermark (unchanged if no
    row was safely later)."""
    now = now or datetime.now(timezone.utc)
    inserts = updates = skipped = 0
    values: list[str] = []
    for row in rows:
        key = business_key(row, key_fields)
        if key is None:
            skipped += 1
            continue
        # xmax = 0 only on a freshly inserted row — the standard upsert insert-vs-update probe
        cur.execute(
            "INSERT INTO ingested_records (id, name, run_id, dataset_id, business_key, "
            "op, ingested_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (dataset_id, business_key) DO UPDATE SET "
            "op = %s, run_id = %s, ingested_at = %s, updated_at = %s "
            "RETURNING (xmax = 0) AS inserted",
            (
                str(uuid4()),
                f"rec:{key}"[:255],
                run_id,
                dataset_id,
                key,
                "insert",
                now,
                now,
                now,
                "update",
                run_id,
                now,
                now,
            ),
        )
        if cur.fetchone()["inserted"]:
            inserts += 1
        else:
            updates += 1
        if cursor_field:
            value = normalize_cursor_value(row.get(cursor_field))
            if value is not None and _acceptable(value, cursor_kind):
                values.append(value)
    return {
        "rows_read": len(rows),
        "rows_written": inserts + updates,
        "inserts": inserts,
        "updates": updates,
        "skipped_no_key": skipped,
        "new_watermark": (
            _advance(values, watermark, cursor_kind, page_full)
            if cursor_field
            else watermark
        ),
    }
