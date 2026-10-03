"""Cursor-ingest orchestration, split enqueue ⊥ execute (doc §1 API⊥worker).

``create_pending_run`` validates and enqueues (a ``pending`` runs row, no egress — safe for the
API in worker mode); ``execute_run`` atomically claims (pending→running) and executes: bootstrap
a delta_cursor on first run (the first non-key temporal field whose name contains, case-
insensitively, ``lastmodified`` then ``modified`` then ``updated`` then ``changed``, failing
those the first containing ``created``, failing those the first temporal field; kind
``timestamp``; datasets with no temporal field ingest full pages each run — the op-log unique
key keeps that idempotent), build the watermark page URL (``ge`` filter — rows sharing the
watermark are re-read, and the business-key upsert keeps that duplicate-free; ``$orderby`` is
the cursor field followed by the business-key fields, so a tie group keeps one stable order
across pages), then fetch + apply page by page through the fixture-tested
mapper/filters/cursor modules: every page is fetched through the egress module (destination
policy and credentials apply to each page). A server ``@odata.nextLink`` takes precedence when
present and is followed (a nextLink off the endpoint's origin fails the run before that page is
requested); a FULL page (as served) without a nextLink does NOT end the run — the run requests
the next page itself: the run's first page URL with ``$skip`` = the entries the server has
SERVED so far in this run (same ``$filter``, ``$orderby`` and ``$top``), counting the served
entries before any run-cap truncation so a capped page never shifts the offset or reads as not
full, and continues until the run has read ``INGEST_MAX_ROWS_PER_RUN`` rows (read from the
environment at call time) or a page holds fewer than ``_PAGE_SIZE`` entries; a full page with
no dict row fails the run rather than spin. The watermark advances only once, after every page
of the run has been stored — to the last fully exhausted cursor value, never to or past a tie
group cut by the row cap or by a full final page (a run that stops at the cap with a full last
page, as served, is a cut, exactly as when a nextLink remains); a run that fails part-way
leaves the watermark unchanged. It then finalizes the run,
and on success fires the §6 automatic
pass: profile + re-score this source's suggestions. ``start_run`` composes both for the interim
in-API executor; the worker (``app.worker``) calls the same ``execute_run`` — identical rows
either way, so nothing is thrown away when execution moves out of the API. Fetch is factored
out so tests substitute a fixture without the network.
"""

import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.egress.http import _effective_origin, fetch_bytes, resolve_fetch_timeout
from app.ingest.cursor import _acceptable, _later, apply_rows
from app.ingest.filters import build_page_url
from app.ingest.mapper import business_key, extract_entries, normalize_cursor_value
from app.profiling.service import profile_source
from app.repositories.runs_postgres_repository import RunPostgresRepository

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_TEMPORAL_MARKERS = ("date", "time")
# Bootstrap cursor-name priority (case-insensitive substring): the freshest-changed field
# wins, falling back to a creation date, then any temporal field.
_CURSOR_NAME_MARKERS = ("lastmodified", "modified", "updated", "changed", "created")

_MAX_ROWS_ENV = "INGEST_MAX_ROWS_PER_RUN"
_DEFAULT_MAX_ROWS_PER_RUN = 50000


class IngestError(Exception):
    """An ingest precondition failed (no dataset, no endpoint, no key fields, ...)."""


def _fetch_timeout_for(connection: dict) -> int | None:
    """The connection's fetch timeout: None when ``timeout_seconds`` is NULL,
    else the stored value validated against 1-600. Raises IngestError
    naming the ``timeout_seconds`` field for a stored value out of range."""
    stored = connection.get("timeout_seconds")
    if stored is None:
        return None
    try:
        return resolve_fetch_timeout(stored)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc


def _fetch_page(url: str, timeout: int = 30) -> bytes:
    """Fetch a raw data page. Factored out so tests can substitute a fixture without the network."""
    return fetch_bytes(url, timeout=timeout)


def _max_rows_per_run() -> int:
    """The run's row cap, read from the environment at call time (a change takes effect on the
    next run without a restart). A non-integer or non-positive value falls back to the default
    rather than failing the run."""
    raw = os.environ.get(_MAX_ROWS_ENV)
    if raw is None:
        return _DEFAULT_MAX_ROWS_PER_RUN
    try:
        limit = int(raw)
    except ValueError:
        return _DEFAULT_MAX_ROWS_PER_RUN
    return limit if limit > 0 else _DEFAULT_MAX_ROWS_PER_RUN


def _page_next_link(raw: bytes) -> str | None:
    """The page's ``@odata.nextLink`` continuation pointer, or None when this page ends the set.
    A link that is present but not a non-empty string is hostile payload — fail loud (the run
    lands status=failed and the watermark stays put) rather than guess at a URL."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    link = data.get("@odata.nextLink")
    if link is None:
        return None
    if not isinstance(link, str):
        raise IngestError("@odata.nextLink is not a string")
    link = link.strip()
    return link or None


def _check_next_link(endpoint: str, next_link: str) -> None:
    """Fail the run, BEFORE the page is requested, when a nextLink leaves the connection
    endpoint's origin — its scheme, host, and effective port must all match (default ports
    normalized, like the egress origin checks). The destination policy and the credential were
    resolved for the endpoint, not for an arbitrary host the payload may point at."""
    source = _effective_origin(endpoint)
    if source is None:
        raise IngestError(
            "connection endpoint is not a fetchable http(s) URL — cannot validate nextLink"
        )
    target = _effective_origin(next_link)
    if target is None:
        raise IngestError("nextLink is not a fetchable http(s) URL")
    if source[0] != target[0]:
        raise IngestError(
            f"nextLink scheme differs from connection endpoint: "
            f"'{target[0]}' != '{source[0]}'"
        )
    if source[1] != target[1]:
        raise IngestError(
            f"nextLink host differs from connection endpoint: "
            f"'{target[1]}' != '{source[1]}'"
        )
    if source[2] != target[2]:
        raise IngestError(
            f"nextLink port differs from connection endpoint: "
            f"{target[2]} != {source[2]}"
        )


def _max_of(values: list[str], cursor_kind: str | None) -> str:
    """The greatest of *values* under the kind-aware ordering (cursor._later)."""
    best = values[0]
    for value in values[1:]:
        if _later(value, best, cursor_kind):
            best = value
    return best


def _run_watermark(
    page_values: list[list[str]],
    current: str | None,
    cursor_kind: str | None,
    capped: bool,
    last_page_full: bool,
) -> str | None:
    """The run's watermark after ALL of its pages have been stored — the advance lands once, at
    the end of the run, so a run that fails part-way leaves the watermark unchanged. An
    exhausted set whose last page was not full means every read row is fully ingested: the
    watermark is the greatest value read. When the run stopped on a CUT final page — the row cap
    hit with a nextLink still pending, or a FULL page (a full page may have cut its max value's
    tie group at the $top boundary) — the last page's greatest value may be a partially read tie
    group: the watermark then advances only to the last fully exhausted timestamp, the greatest
    read value strictly below that cut, never to or past it (the at-or-after filter re-reads the
    cut group next run; upserts keep it duplicate-free). When the cut page yielded no admissible
    cursor value at all, the cut value is unknown (a keyless or unnormalizable row at the cut
    may share the last read row's value, whose tie group then continues past the cut), so no tie
    group can be proven fully exhausted — the watermark is left unchanged rather than risk
    landing on or past a partially read value. Never regresses a later watermark; a run with no
    admissible values leaves it unchanged."""
    all_values = [v for values in page_values for v in values]
    if not all_values:
        return current
    if capped or last_page_full:
        if not page_values[-1]:
            # the cut page yielded no admissible cursor values — the cut value is unknown (a
            # keyless row at the cut may share the value of the last read row, whose tie group
            # then continues past the cut), so nothing is provably exhausted
            return current
        cut = _max_of(page_values[-1], cursor_kind)
        candidates = [v for v in all_values if _later(cut, v, cursor_kind)]
        if not candidates:
            # every read value sits at the cut — the tie group continues past the cut and no
            # lower value was read, so the watermark cannot advance
            logger.warning(
                "run stopped on a cut page tied at cursor value %r with no lower value read "
                "— watermark cannot advance (the tie group continues past the cut)",
                cut,
            )
            return current
        candidate = _max_of(candidates, cursor_kind)
    else:
        candidate = _max_of(all_values, cursor_kind)
    return (
        candidate
        if (current is None or _later(candidate, current, cursor_kind))
        else current
    )


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
        "fetch_timeout": _fetch_timeout_for(connection),
        "fields": fields,
        "key_fields": key_fields,
        "cursor_row": dict(cursor_row) if cursor_row else None,
    }


def _bootstrap_cursor(cur, pipeline: dict, fields: list[dict], now) -> dict | None:
    """First run of a pipeline with no delta_cursor: pick the cursor field DETERMINISTICALLY
    among the non-key temporal fields — the first whose name contains, case-insensitively,
    ``lastmodified``, then ``modified``, then ``updated``, then ``changed``; failing those, the
    first containing ``created``; failing those, the first temporal field as today (kind
    ``timestamp``). Returns None when the dataset has no temporal field — the pipeline then
    full-page-ingests each run."""
    temporal = [
        f
        for f in fields
        if not f.get("is_key")
        and any(m in (f.get("data_type") or "").lower() for m in _TEMPORAL_MARKERS)
    ]
    field = None
    for marker in _CURSOR_NAME_MARKERS:
        field = next(
            (f for f in temporal if marker in (f.get("name") or "").lower()), None
        )
        if field is not None:
            break
    if field is None:
        field = temporal[0] if temporal else None
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
        key_names = [f["name"] for f in ctx["key_fields"]]
        url = build_page_url(
            ctx["connection"]["endpoint"],
            dataset["name"],
            _PAGE_SIZE,
            ctx["connection"].get("protocol_version"),
            cursor_field_name,
            watermark,
            cursor_kind,
            key_names,
        )
        max_rows = _max_rows_per_run()
        rows_read = rows_written = skipped_no_key = rows_suppressed = 0
        inserts = updates = 0
        page_values: list[list[str]] = []
        capped = False
        last_page_full = False
        skip_offset = 0
        warned_unstable_order = False
        while True:
            raw = (
                _fetch_page(url)
                if ctx["fetch_timeout"] is None
                else _fetch_page(url, timeout=ctx["fetch_timeout"])
            )
            entries = extract_entries(raw)
            # the cap bounds rows READ: entries beyond the remaining budget are never read, so
            # they count for nothing; the served count, the page-full test, the no-dict-row
            # guard and the $skip offset below all count the entries the server SERVED (before
            # this run-cap truncation) — a capped page must never shift the $skip offset, read
            # as not full, or fail the no-dict-row guard (a junk (non-dict) entry still
            # occupied a $top slot); the offset accumulates EVERY page served so far in this
            # run, nextLink pages included, because the $skip URL is the run's first page URL
            # — the start of the same ordered stream the nextLink pages continued
            served = len(entries)
            served_rows = [r for r in entries if isinstance(r, dict)]
            skip_offset += served
            remaining = max_rows - rows_read
            if remaining < served:
                entries = entries[:remaining]
            rows = [r for r in entries if isinstance(r, dict)]
            page_full = served >= _PAGE_SIZE
            last_page_full = page_full
            with get_cursor() as cur:
                result = apply_rows(
                    cur,
                    run_id,
                    dataset["id"],
                    rows,
                    key_names,
                    cursor_field_name,
                    watermark,
                    cursor_kind,
                    now=now,
                    page_full=page_full,
                )
            rows_read += result["rows_read"]
            rows_written += result["rows_written"]
            skipped_no_key += result["skipped_no_key"]
            rows_suppressed += result["rows_suppressed"]
            inserts += result["inserts"]
            updates += result["updates"]
            if cursor_field_name is not None:
                # mirror apply_rows' candidacy exactly: a keyless row never advances the
                # watermark, a suppressed (erased-subject) row still counts
                values: list[str] = []
                for row in rows:
                    if business_key(row, key_names) is None:
                        continue
                    value = normalize_cursor_value(row.get(cursor_field_name))
                    if value is not None and _acceptable(value, cursor_kind):
                        values.append(value)
                page_values.append(values)
            next_link = _page_next_link(raw)
            if rows_read >= max_rows:
                # the cap cut the run: a FULL final page (as served) may have cut its max
                # value's tie group at the $top boundary, and a pending nextLink always means
                # more rows to come — both read as a cut (the watermark stays below it)
                capped = page_full or next_link is not None
                break
            if next_link is None and not page_full:
                # a not-full page with no nextLink ends the set
                break
            if not served_rows:
                # a page that, as SERVED, holds NO dict row at all: following it — via the
                # server's nextLink or our own $skip — would spin forever; fail loud (the
                # watermark stays put, the run is visible). Judged on the entries the server
                # SERVED, not the cap-truncated slice: a slice left with only non-dict
                # entries is a budget matter (the run keeps paging and stops at the cap),
                # not a page without dict rows
                if next_link is not None:
                    raise IngestError(
                        "page without ingestable rows still carries @odata.nextLink — "
                        "stopping to avoid a paging loop"
                    )
                raise IngestError(
                    "page without ingestable rows is full with no @odata.nextLink — "
                    "stopping to avoid a paging loop"
                )
            if next_link is not None:
                # a server @odata.nextLink takes precedence over our own $skip continuation
                _check_next_link(ctx["connection"]["endpoint"], next_link)
                url = next_link
            else:
                # a FULL page (as served) without a nextLink does not end the set — request
                # the next page ourselves: the run's first page URL with $skip = the entries
                # the server has served so far in this run (same $filter, $orderby, $top)
                if not (cursor_field_name and key_names) and not warned_unstable_order:
                    warned_unstable_order = True
                    logger.warning(
                        "run %s pages with $skip without a guaranteed order (no cursor "
                        "field or no key fields) — rows may repeat or be missed across "
                        "pages",
                        run_id,
                    )
                url = build_page_url(
                    ctx["connection"]["endpoint"],
                    dataset["name"],
                    _PAGE_SIZE,
                    ctx["connection"].get("protocol_version"),
                    cursor_field_name,
                    watermark,
                    cursor_kind,
                    key_names,
                    skip=skip_offset,
                )
        # the watermark advance lands ONCE, after every page of the run has been stored — a
        # run that failed part-way (caught below) never reaches this point, so its watermark
        # is left unchanged
        new_watermark = _run_watermark(
            page_values, watermark, cursor_kind, capped, last_page_full
        )
        finished = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = %s, rows_read = %s, rows_written = %s, "
                "rows_suppressed = %s, "
                "finished_at = %s, updated_at = %s WHERE id = %s AND status = 'running'",
                (
                    "succeeded",
                    rows_read,
                    rows_written,
                    rows_suppressed,
                    finished,
                    finished,
                    run_id,
                ),
            )
            if cur.rowcount == 0:
                # status guard: if the reaper (or an admin) finalized this run while we
                # executed, the terminal state wins — a zombie executor must not resurrect a
                # reaped row, and its watermark advance must not land either (the op-log rows
                # it wrote are idempotent upserts and stay, which is safe)
                logger.warning(
                    "run %s was finalized externally while executing — discarding this "
                    "executor's bookkeeping (op-log upserts already applied, idempotent)",
                    run_id,
                )
                return _run_body(
                    repo,
                    run_id,
                    inserts=inserts,
                    updates=updates,
                    skipped_no_key=skipped_no_key,
                )
            if cursor_row is not None and cursor_field_name is not None:
                cur.execute(
                    "UPDATE delta_cursors SET cursor_value = %s, last_run_id = %s, "
                    "updated_at = %s WHERE id = %s",
                    (new_watermark, run_id, finished, cursor_row["id"]),
                )
    except Exception as exc:
        # any failure after the claim — context drift, fetch, parse, nextLink validation,
        # watermark rendering, or an apply transaction (rolled back by get_cursor) — must
        # land ON the run, never leave it stuck at status='running'; the watermark advance
        # happens only in the final bookkeeping, so a failed run leaves it unchanged
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
        inserts=inserts,
        updates=updates,
        skipped_no_key=skipped_no_key,
        cursor_value=new_watermark,
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
