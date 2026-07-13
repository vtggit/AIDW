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
from app.governance.hashing import subject_key_hash
from app.ingest.mapper import business_key, parse_rows
from app.pii.engine import pii_fingerprint
from app.pii.service import reconcile_flags_for_dataset
from app.pii.values import categories_above_floor
from app.suggestion.rescore import rescore_for_source

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 200
_PROFILE_TIER = "profile"


def _pii_candidates_from_sample(fields: list[dict], rows: list[dict]) -> list[dict]:
    """Profile-tier PII candidates: run the value detectors over each field's sampled values and
    emit a candidate for every category clearing the match-ratio floor. Confidence rises with the
    match ratio and always exceeds the schema-tier band (value evidence beats a name guess).
    """
    candidates = []
    for f in fields:
        values = [r.get(f["name"]) for r in rows]
        for category, ratio in categories_above_floor(values).items():
            candidates.append(
                {
                    "field_name": f["name"],
                    "category": category,
                    "confidence": round(0.8 + 0.2 * ratio, 2),
                    "rationale": (
                        f"profile: {round(ratio * 100)}% of sampled values match the "
                        f"{category} format"
                    ),
                    "detection_tier": _PROFILE_TIER,
                    "fingerprint": pii_fingerprint(f["name"], category),
                }
            )
    return candidates


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


def _stats(
    rows: list[dict], field_name: str, value_rows: list[dict] | None = None
) -> dict:
    """Per-field stats over the sample. All value handling is string-based so mixed/None/nested
    values never raise; distinct/min/max/most-common are computed on the string projection.

    Aggregate COUNTS (row/null/distinct) come from ``rows``; VALUE columns (min/max/most_common)
    come from ``value_rows`` (defaults to ``rows``). RTBF suppression passes value_rows with the
    erased subjects removed, so a re-profile drops their values while the non-personal counts stay
    full-sample — matching the erasure convention (executor + pii._scrub_profile keep the counts
    and NULL only the value columns).
    """
    value_rows = rows if value_rows is None else value_rows
    present = [r.get(field_name) for r in rows]
    keys = [str(v) for v in present if v is not None]
    row_count = len(present)
    null_count = row_count - len(keys)
    value_keys = [
        str(v) for v in (r.get(field_name) for r in value_rows) if v is not None
    ]

    def _cap(s):
        return s[:255] if s is not None else None

    most_common = Counter(value_keys).most_common(1)[0][0] if value_keys else None
    return {
        "row_count": row_count,
        "null_count": null_count,
        "distinct_count": len(set(keys)),
        "min_value": _cap(min(value_keys)) if value_keys else None,
        "max_value": _cap(max(value_keys)) if value_keys else None,
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
    pii_flagged = 0
    with get_cursor() as cur:
        for ds in datasets:
            cur.execute(
                "SELECT id, name, is_key FROM discovered_fields WHERE dataset_id = %s "
                "ORDER BY field_position NULLS LAST, name",
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

            # profile-tier PII detection over the sample, reconciled into pii_flags in this same
            # transaction (a column that IS emails flags regardless of its name). Deliberately runs
            # over the FULL rows (pre-RTBF-suppression): a field's PII status is a column property
            # and must not depend on one subject's erasure; it stores only category/ratio/field-name,
            # never a raw value, so an erased subject cannot leak through here.
            candidates = _pii_candidates_from_sample(fields, rows)
            counts = reconcile_flags_for_dataset(
                cur, ds["id"], fields, candidates, _PROFILE_TIER, now
            )
            pii_flagged += counts["created"] + counts["upgraded"]

            # detect-before-write suppression: a field carrying ANY active flag (schema or
            # profile tier) gets its example values withheld BEFORE the profile is written, so
            # new profiling never persists raw PII values (zero leak window)
            cur.execute(
                "SELECT DISTINCT discovered_field_id FROM pii_flags WHERE dataset_id = %s "
                "AND status IN ('flagged', 'confirmed') AND discovered_field_id IS NOT NULL",
                (ds["id"],),
            )
            flagged_ids = {r["discovered_field_id"] for r in cur.fetchall()}

            # RTBF (#76): drop erased subjects BEFORE value-stats, so a re-profile never
            # resurrects an erased subject's min/max/most_common from the live source (which may
            # still hold them). Mirrors the ingest filter (cursor.apply_rows): hash ONLY when the
            # dataset actually has suppression entries (no pepper needed otherwise); a missing
            # pepper then raises and rolls back this whole transaction rather than resurrecting.
            # Key derivation (is_key fields in field_position order) matches ingest exactly, so the
            # hashes line up with what the erasure recorded.
            cur.execute(
                "SELECT key_hash FROM suppression_entries WHERE dataset_id = %s",
                (ds["id"],),
            )
            suppressed = {r["key_hash"] for r in cur.fetchall()}
            stats_rows = rows
            if suppressed:
                key_field_names = [fld["name"] for fld in fields if fld.get("is_key")]
                stats_rows = []
                for r in rows:
                    bk = business_key(r, key_field_names)
                    if bk is not None and subject_key_hash(ds["id"], bk) in suppressed:
                        continue  # erased subject: excluded from value-stats
                    stats_rows.append(r)

            for f in fields:
                # counts over the full sample (non-personal aggregates, kept); value columns over
                # stats_rows (erased subjects removed) — see _stats and the erasure convention
                st = _stats(rows, f["name"], value_rows=stats_rows)
                if f["id"] in flagged_ids:
                    st = {
                        **st,
                        "min_value": None,
                        "max_value": None,
                        "most_common_value": None,
                    }
                _upsert_profile(cur, f["id"], st, now)
                profiled_fields += 1

    rescore = rescore_for_source(source_id)
    return {
        "source_id": source_id,
        "datasets_profiled": profiled_datasets,
        "fields_profiled": profiled_fields,
        "pii_fields_flagged": pii_flagged,
        **rescore,
    }
