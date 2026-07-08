"""Interim data-profiling orchestration (in-API egress path).

Loads a source's connection endpoint, fetches a sampled data page per dataset (``GET {set}?$top=N``),
computes per-field statistics into ``field_profiles``, and triggers the profile-tier re-score. Fetch
+ parse are factored out so tests can substitute a fixture without hitting the network. Idempotent:
a re-run updates each field's single profile row (keyed on discovered_field_id).
"""

import logging
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.ingest.mapper import parse_rows
from app.suggestion.rescore import rescore_for_source

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 200


class ProfilingError(Exception):
    """A profiling precondition failed (e.g. the source has no connection endpoint)."""


def _fetch_rows(url: str) -> bytes:
    """Fetch a raw data page. Factored out so tests can substitute a fixture without the network."""
    return urllib.request.urlopen(url, timeout=30).read()


def _parse_rows(raw: bytes) -> list[dict]:
    """Extract the row list from an OData JSON payload — V4 (``value``) or V2 (``d.results``).
    Delegates to the shared ingest mapper so the V2/V4 payload shapes live in one place.
    """
    return parse_rows(raw)


def _stats(rows: list[dict], field_name: str) -> dict:
    """Per-field stats over the sample. All value handling is string-based so mixed/None/nested
    values never raise; distinct/min/max/most-common are computed on the string projection.
    """
    present = [r.get(field_name) for r in rows]
    keys = [str(v) for v in present if v is not None]
    row_count = len(present)
    null_count = row_count - len(keys)

    def _cap(s):
        return s[:255] if s is not None else None

    most_common = Counter(keys).most_common(1)[0][0] if keys else None
    return {
        "row_count": row_count,
        "null_count": null_count,
        "distinct_count": len(set(keys)),
        "min_value": _cap(min(keys)) if keys else None,
        "max_value": _cap(max(keys)) if keys else None,
        "most_common_value": _cap(most_common),
    }


def _upsert_profile(cur, discovered_field_id: str, st: dict, now) -> None:
    cur.execute(
        "SELECT id FROM field_profiles WHERE discovered_field_id = %s",
        (discovered_field_id,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE field_profiles SET row_count = %s, null_count = %s, distinct_count = %s, "
            "min_value = %s, max_value = %s, most_common_value = %s, updated_at = %s WHERE id = %s",
            (
                st["row_count"],
                st["null_count"],
                st["distinct_count"],
                st["min_value"],
                st["max_value"],
                st["most_common_value"],
                now,
                row["id"],
            ),
        )
    else:
        cur.execute(
            "INSERT INTO field_profiles (id, name, discovered_field_id, row_count, null_count, "
            "distinct_count, min_value, max_value, most_common_value, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                str(uuid4()),
                f"profile:{discovered_field_id}",
                discovered_field_id,
                st["row_count"],
                st["null_count"],
                st["distinct_count"],
                st["min_value"],
                st["max_value"],
                st["most_common_value"],
                now,
                now,
            ),
        )


def profile_source(source_id: str) -> dict:
    """Profile every dataset of a source into field_profiles, then re-score its suggestions. Raises
    LookupError if the source is missing, ProfilingError if it isn't profilable."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM sources WHERE id = %s", (source_id,))
        if cur.fetchone() is None:
            raise LookupError("source not found")
        cur.execute(
            "SELECT * FROM source_connections WHERE source_id = %s ORDER BY created_at LIMIT 1",
            (source_id,),
        )
        conn = cur.fetchone()
        cur.execute("SELECT id, name FROM datasets WHERE source_id = %s", (source_id,))
        datasets = [dict(r) for r in cur.fetchall()]

    if conn is None or not (conn.get("endpoint") or "").strip():
        raise ProfilingError("source has no source_connections endpoint to profile")
    base = conn["endpoint"].rstrip("/")

    now = datetime.now(timezone.utc)
    profiled_fields = 0
    profiled_datasets = 0
    with get_cursor() as cur:
        for ds in datasets:
            cur.execute(
                "SELECT id, name FROM discovered_fields WHERE dataset_id = %s",
                (ds["id"],),
            )
            fields = [dict(r) for r in cur.fetchall()]
            if not fields:
                continue
            url = f"{base}/{urllib.parse.quote(ds['name'])}?$top={_SAMPLE_SIZE}&$format=json"
            try:
                rows = _parse_rows(_fetch_rows(url))
            except Exception:
                logger.exception("profiling fetch failed for dataset %s", ds["name"])
                continue
            profiled_datasets += 1
            for f in fields:
                _upsert_profile(cur, f["id"], _stats(rows, f["name"]), now)
                profiled_fields += 1

    rescore = rescore_for_source(source_id)
    return {
        "source_id": source_id,
        "datasets_profiled": profiled_datasets,
        "fields_profiled": profiled_fields,
        **rescore,
    }
