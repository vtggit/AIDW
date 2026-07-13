"""Cursor-ingest orchestration, split enqueue ⊥ execute (doc §1 API⊥worker).

``create_pending_run`` validates and enqueues (a ``pending`` runs row, no egress — safe for the
API in worker mode); ``execute_run`` atomically claims (pending→running) and executes: bootstrap a
delta_cursor on first run (first non-key temporal field, kind ``timestamp``; datasets with no
temporal field ingest full pages each run — the op-log unique key keeps that idempotent), build
the watermark page URL, fetch + apply through the fixture-tested mapper/filters/cursor modules,
finalize the run, and on success fire the §6 automatic pass: profile + re-score this source's
suggestions. ``start_run`` composes both for the interim in-API executor; the worker
(``app.worker``) calls the same ``execute_run`` — identical rows either way, so nothing is thrown
away when execution moves out of the API. Fetch is factored out so tests substitute a fixture
without the network.
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


def create_pending_run(pipeline_id: str, trigger: str = "manual") -> dict:
    """Validate the pipeline's preconditions and enqueue ONE pending run (no egress happens
    here — the API can call this in worker mode). Raises LookupError (unknown pipeline) /
    IngestError (bad preconditions) BEFORE any run row exists. Edge: if the inline caller dies
    between this commit and its claim, the row stays visible as ``pending`` residue — it is NOT
    auto-reaped (a down worker's backlog must survive a restart); an admin can delete it.
    """
    ctx = _load_context(pipeline_id)
    now = datetime.now(timezone.utc)
    run_id = str(uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO runs (id, name, pipeline_id, status, trigger, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                run_id,
                f"ingest:{ctx['pipeline']['name']}"[:255],
                pipeline_id,
                "pending",
                trigger,
                now,
                now,
            ),
        )
    return RunPostgresRepository().get_by_id(run_id)


def execute_run(run_id: str, claimed: bool = False) -> dict | None:
    """Claim (pending→running, atomic — exactly one executor wins) and execute one run; pass
    ``claimed=True`` when the caller already flipped the row (the worker's SKIP LOCKED claim).
    Returns None when the run was not claimable (unknown id, or another executor got it).
    ANY failure after the claim (context drift, fetch, parse, watermark rendering, the apply
    transaction itself) is recorded ON the run (status=failed, error_detail) rather than
    raised — a committed 'running' row must never be left behind."""
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        if claimed:
            cur.execute(
                "SELECT pipeline_id FROM runs WHERE id = %s AND status = 'running'",
                (run_id,),
            )
        else:
            cur.execute(
                "UPDATE runs SET status = 'running', started_at = %s, updated_at = %s "
                "WHERE id = %s AND status = 'pending' RETURNING pipeline_id",
                (now, now, run_id),
            )
        row = cur.fetchone()
    if row is None:
        return None

    repo = RunPostgresRepository()
    try:
        if not row["pipeline_id"]:
            raise IngestError("run has no pipeline_id (pipeline deleted after enqueue)")
        ctx = _load_context(row["pipeline_id"])
    except Exception as exc:
        # at execute time the run row already exists, so EVERYTHING — context drift (pipeline/
        # dataset/endpoint/key-fields gone since enqueue) AND unexpected errors (db blips,
        # timeouts) — lands ON the run instead of raising; a narrower catch here would leave a
        # committed 'running' row stuck when _load_context itself fails
        return _finalize_failed(repo, run_id, exc)

    pipeline, dataset = ctx["pipeline"], ctx["dataset"]
    cursor_row = ctx["cursor_row"]
    try:
        if cursor_row is None:
            with get_cursor() as cur:
                cursor_row = _bootstrap_cursor(cur, pipeline, ctx["fields"], now)
    except Exception as exc:
        return _finalize_failed(repo, run_id, exc)

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
            # status guard: if the reaper (or an admin) finalized this run while we executed,
            # the terminal state wins — a zombie executor must not resurrect a reaped row,
            # and its watermark advance must not land either (the op-log rows it wrote are
            # idempotent upserts and stay, which is safe)
            cur.execute(
                "UPDATE runs SET status = %s, rows_read = %s, rows_written = %s, "
                "rows_suppressed = %s, "
                "finished_at = %s, updated_at = %s WHERE id = %s AND status = 'running'",
                (
                    "succeeded",
                    result["rows_read"],
                    result["rows_written"],
                    result["rows_suppressed"],
                    finished,
                    finished,
                    run_id,
                ),
            )
            if cur.rowcount == 0:
                logger.warning(
                    "run %s was finalized externally while executing — discarding this "
                    "executor's bookkeeping (op-log upserts already applied, idempotent)",
                    run_id,
                )
                return _run_body(
                    repo,
                    run_id,
                    inserts=result["inserts"],
                    updates=result["updates"],
                    skipped_no_key=result["skipped_no_key"],
                )
            if cursor_row is not None and cursor_field_name is not None:
                cur.execute(
                    "UPDATE delta_cursors SET cursor_value = %s, last_run_id = %s, "
                    "updated_at = %s WHERE id = %s",
                    (result["new_watermark"], run_id, finished, cursor_row["id"]),
                )
    except Exception as exc:
        # any failure after the claim — fetch, parse, watermark rendering, or the apply
        # transaction (rolled back by get_cursor) — must land ON the run, never leave it
        # stuck at status='running'
        return _finalize_failed(repo, run_id, exc)

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

    body = _run_body(
        repo,
        run_id,
        inserts=result["inserts"],
        updates=result["updates"],
        skipped_no_key=result["skipped_no_key"],
        cursor_value=result["new_watermark"],
    )
    if profile is not None:
        body["profile"] = profile
    if profile_error is not None:
        body["profile_error"] = profile_error
    return body


def _run_body(repo, run_id: str, **extras) -> dict:
    """The run row spread with executor extras. A row deleted externally mid-flight (the
    deletion flavor of external finalization) yields a stub instead of a None-spread crash.
    """
    row = repo.get_by_id(run_id)
    if row is None:
        logger.warning("run %s was deleted externally while executing", run_id)
        row = {"id": run_id, "status": "deleted"}
    return {**row, **extras}


def _finalize_failed(repo, run_id: str, exc: Exception) -> dict:
    """Record a post-claim failure ON the run and return the failed run body. Status-guarded:
    a row already finalized externally (reaper, admin) keeps its terminal state."""
    logger.exception("ingest run %s failed", run_id)
    finished = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE runs SET status = %s, error_detail = %s, finished_at = %s, "
            "updated_at = %s WHERE id = %s AND status = 'running'",
            ("failed", str(exc)[:1024], finished, finished, run_id),
        )
    return _run_body(repo, run_id, inserts=0, updates=0, skipped_no_key=0)


def start_run(pipeline_id: str, trigger: str = "manual") -> dict:
    """Enqueue + execute synchronously — the interim in-API executor path, contract unchanged:
    LookupError/IngestError raise BEFORE any run row exists; every later failure lands ON the
    run. The worker path calls the same execute_run against rows it claimed itself."""
    pending = create_pending_run(pipeline_id, trigger)
    body = execute_run(pending["id"])
    if (
        body is None
    ):  # another executor raced us to the claim — report the row as it stands
        return _run_body(RunPostgresRepository(), pending["id"])
    return body
