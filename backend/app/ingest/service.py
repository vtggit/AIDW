"""Cursor-ingest orchestration (interim in-API egress path).

Composes the three fixture-tested modules — filters (page URL from watermark), mapper (page →
rows), cursor (op-log + watermark transaction) — into one run of a pipeline: load the pipeline's
dataset/connection/key fields, bootstrap a delta_cursor on first run (first non-key temporal
field, kind ``timestamp``; datasets with no temporal field ingest full pages each run — the op-log
unique key keeps that idempotent), record a ``runs`` row around the fetch, and on success fire the
§6 automatic pass: profile + re-score this source's suggestions. Fetch is factored out so tests
substitute a fixture without the network. The Milestone 6 worker migrates this logic unchanged.
"""

import logging
import urllib.request
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.ingest.cursor import apply_rows
from app.ingest.filters import build_page_url
from app.ingest.mapper import extract_entries
from app.profiling.service import profile_source
from app.repositories.runs_postgres_repository import RunPostgresRepository

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_TEMPORAL_MARKERS = ("date", "time")


class IngestError(Exception):
    """An ingest precondition failed (no dataset, no endpoint, no key fields, ...)."""


def _fetch_page(url: str) -> bytes:
    """Fetch a raw data page. Factored out so tests can substitute a fixture without the network."""
    return urllib.request.urlopen(url, timeout=30).read()


def _load_context(pipeline_id: str) -> dict:
    """Load and validate everything one run needs. Raises LookupError for an unknown pipeline and
    IngestError for a pipeline that is not ingestable yet."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM pipelines WHERE id = %s", (pipeline_id,))
        pipeline = cur.fetchone()
        if pipeline is None:
            raise LookupError("pipeline not found")
        pipeline = dict(pipeline)
        if not pipeline.get("dataset_id"):
            raise IngestError("pipeline has no dataset_id to ingest")
        cur.execute("SELECT * FROM datasets WHERE id = %s", (pipeline["dataset_id"],))
        dataset = cur.fetchone()
        if dataset is None:
            raise IngestError("pipeline's dataset no longer exists")
        dataset = dict(dataset)
        if not dataset.get("source_id"):
            raise IngestError("dataset has no source_id")
        cur.execute(
            "SELECT * FROM source_connections WHERE source_id = %s ORDER BY created_at LIMIT 1",
            (dataset["source_id"],),
        )
        connection = cur.fetchone()
        cur.execute(
            "SELECT * FROM discovered_fields WHERE dataset_id = %s "
            "ORDER BY field_position NULLS LAST, name",
            (dataset["id"],),
        )
        fields = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT * FROM delta_cursors WHERE pipeline_id = %s ORDER BY created_at LIMIT 1",
            (pipeline_id,),
        )
        cursor_row = cur.fetchone()

    if connection is None or not (connection.get("endpoint") or "").strip():
        raise IngestError("source has no source_connections endpoint to ingest from")
    key_fields = [f for f in fields if f.get("is_key")]
    if not key_fields:
        raise IngestError("dataset has no key fields to derive business keys from")
    return {
        "pipeline": pipeline,
        "dataset": dataset,
        "connection": dict(connection),
        "fields": fields,
        "key_fields": key_fields,
        "cursor_row": dict(cursor_row) if cursor_row else None,
    }


def _bootstrap_cursor(cur, pipeline: dict, fields: list[dict], now) -> dict | None:
    """First run of a pipeline with no delta_cursor: pick the first non-key temporal field as the
    cursor (kind timestamp). Returns None when the dataset has no temporal field — the pipeline
    then full-page-ingests each run."""
    field = next(
        (
            f
            for f in fields
            if not f.get("is_key")
            and any(m in (f.get("data_type") or "").lower() for m in _TEMPORAL_MARKERS)
        ),
        None,
    )
    if field is None:
        return None
    row = {
        "id": str(uuid4()),
        "name": f"cursor:{pipeline['name']}"[:255],
        "pipeline_id": pipeline["id"],
        "cursor_field_id": field["id"],
        "cursor_kind": "timestamp",
        "cursor_value": None,
    }
    cur.execute(
        "INSERT INTO delta_cursors (id, name, pipeline_id, cursor_field_id, cursor_kind, "
        "cursor_value, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            row["id"],
            row["name"],
            row["pipeline_id"],
            row["cursor_field_id"],
            row["cursor_kind"],
            row["cursor_value"],
            now,
            now,
        ),
    )
    return row


def start_run(pipeline_id: str) -> dict:
    """Execute one cursor-ingest run of a pipeline and return the finished run record plus the
    observable counts. Raises LookupError (unknown pipeline) / IngestError (bad preconditions)
    BEFORE any run row exists; ANY failure after the run row exists (fetch, parse, watermark
    rendering, the apply transaction itself) is recorded ON the run (status=failed, error_detail)
    rather than raised — a committed 'running' row must never be left behind."""
    ctx = _load_context(pipeline_id)
    pipeline, dataset = ctx["pipeline"], ctx["dataset"]
    now = datetime.now(timezone.utc)
    run_id = str(uuid4())

    with get_cursor() as cur:
        cursor_row = ctx["cursor_row"]
        if cursor_row is None:
            cursor_row = _bootstrap_cursor(cur, pipeline, ctx["fields"], now)
        cur.execute(
            "INSERT INTO runs (id, name, pipeline_id, status, trigger, started_at, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                run_id,
                f"ingest:{pipeline['name']}"[:255],
                pipeline_id,
                "running",
                "manual",
                now,
                now,
                now,
            ),
        )

    fields_by_id = {f["id"]: f for f in ctx["fields"]}
    cursor_field_name = None
    cursor_kind = None
    watermark = None
    if cursor_row is not None:
        cursor_field = fields_by_id.get(cursor_row.get("cursor_field_id"))
        if cursor_field is not None:
            cursor_field_name = cursor_field["name"]
            cursor_kind = cursor_row.get("cursor_kind")
            watermark = cursor_row.get("cursor_value")
        else:
            # the cursor field was deleted (FK SET NULL) or points outside this dataset —
            # degrade to an unfiltered page and DO NOT touch the stored cursor row
            logger.warning(
                "delta_cursor %s has no resolvable cursor field — ingesting unfiltered",
                cursor_row["id"],
            )

    repo = RunPostgresRepository()
    try:
        url = build_page_url(
            ctx["connection"]["endpoint"],
            dataset["name"],
            _PAGE_SIZE,
            ctx["connection"].get("protocol_version"),
            cursor_field_name,
            watermark,
            cursor_kind,
        )
        # page_full must count entries AS FETCHED — a junk (non-dict) entry still occupied a
        # $top slot, so judging fullness on the dict-filtered rows would miss a capped page
        entries = extract_entries(_fetch_page(url))
        rows = [r for r in entries if isinstance(r, dict)]
        with get_cursor() as cur:
            result = apply_rows(
                cur,
                run_id,
                dataset["id"],
                rows,
                [f["name"] for f in ctx["key_fields"]],
                cursor_field_name,
                watermark,
                cursor_kind,
                now=now,
                page_full=len(entries) >= _PAGE_SIZE,
            )
            finished = datetime.now(timezone.utc)
            cur.execute(
                "UPDATE runs SET status = %s, rows_read = %s, rows_written = %s, "
                "finished_at = %s, updated_at = %s WHERE id = %s",
                (
                    "succeeded",
                    result["rows_read"],
                    result["rows_written"],
                    finished,
                    finished,
                    run_id,
                ),
            )
            if cursor_row is not None and cursor_field_name is not None:
                cur.execute(
                    "UPDATE delta_cursors SET cursor_value = %s, last_run_id = %s, "
                    "updated_at = %s WHERE id = %s",
                    (result["new_watermark"], run_id, finished, cursor_row["id"]),
                )
    except Exception as exc:
        # any failure after the committed run row — fetch, parse, watermark rendering, or the
        # apply transaction (rolled back by get_cursor) — must land ON the run, never leave it
        # stuck at status='running'
        logger.exception("ingest run failed for pipeline %s", pipeline_id)
        finished = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = %s, error_detail = %s, finished_at = %s, "
                "updated_at = %s WHERE id = %s",
                ("failed", str(exc)[:1024], finished, finished, run_id),
            )
        return {
            **repo.get_by_id(run_id),
            "inserts": 0,
            "updates": 0,
            "skipped_no_key": 0,
        }

    # §6 automatic trigger: on ingest-run success, a profile + re-score pass. Best-effort — a
    # profiling failure must not fail an already-succeeded ingest run.
    profile = None
    profile_error = None
    try:
        profile = profile_source(dataset["source_id"])
    except Exception as exc:
        logger.exception(
            "post-ingest profiling failed for source %s", dataset["source_id"]
        )
        profile_error = str(exc)

    body = {
        **repo.get_by_id(run_id),
        "inserts": result["inserts"],
        "updates": result["updates"],
        "skipped_no_key": result["skipped_no_key"],
        "cursor_value": result["new_watermark"],
    }
    if profile is not None:
        body["profile"] = profile
    if profile_error is not None:
        body["profile_error"] = profile_error
    return body
