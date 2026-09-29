"""Issue #632 — the stranded-scheduled reaper UPDATE gets a partial index.

Proves, with no application code changes:
1. after the migrations, ``idx_sequence_runs_stranded_scheduled`` exists on
   sequence_runs with the predicate triggered_by = 'schedule' AND
   COALESCE(status, 'pending') = 'pending' AND started_at IS NOT NULL (via
   pg_indexes; the predicate was realigned by #648);
2. EXPLAIN of the reaper's own UPDATE statement (read from app/worker/loop.py) names
   that index when run in the test's own transaction with
   ``SET LOCAL enable_seqscan = off`` (tables are tiny in tests).
"""

import ast
import pathlib
import re
from datetime import datetime, timezone

import psycopg2
import pytest

INDEX_NAME = "idx_sequence_runs_stranded_scheduled"
_LOOP_PY = pathlib.Path(__file__).resolve().parents[1] / "app" / "worker" / "loop.py"


def _reaper_update_statement() -> str:
    """Return the UPDATE statement reap_stranded_scheduled executes, straight from source."""
    tree = ast.parse(_LOOP_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.FunctionDef)
            or node.name != "reap_stranded_scheduled"
        ):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call) or not call.args:
                continue
            first = call.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if re.match(
                    r"\s*UPDATE\s+sequence_runs\s+SET\s+started_at\s*=\s*NULL\b",
                    first.value,
                    re.IGNORECASE,
                ):
                    return first.value
    raise AssertionError("reaper UPDATE statement not found in app/worker/loop.py")


def _canonicalize(indexdef: str) -> str:
    """Whitespace-normalized indexdef with Postgres's cosmetic type casts and
    parentheses removed, so predicate assertions do not depend on formatting.

    Postgres renders predicate literals with the column's declared type, so strip
    every cosmetic cast (issue #648: the COALESCE predicate comes back as
    ``(COALESCE(status, 'pending'::character varying))::text = 'pending'::text``),
    not only ``::text``."""
    text = re.sub(
        r"::\s*(?:text|character\s+varying|character|varchar)(?:\s*\(\s*\d+\s*\))?",
        "",
        indexdef,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[(),\s]+", " ", text)


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_issue632_freeform():
    from app.db.connection import get_connection_params

    statement = _reaper_update_statement()
    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            # 1. The migration created the partial index with the reaper's predicate.
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("sequence_runs", INDEX_NAME),
            )
            rows = cur.fetchall()
            assert (
                len(rows) == 1
            ), f"index {INDEX_NAME} missing on sequence_runs after migration"
            indexdef = re.sub(r"\s+", " ", rows[0][0])
            assert re.search(r"\bON\s+\S*sequence_runs\b", indexdef)
            assert "(updated_at)" in indexdef
            predicate = _canonicalize(indexdef)
            assert "triggered_by = 'schedule'" in predicate
            # #648: NULL status means pending (COALESCE), no bare equality
            assert "COALESCE status 'pending' = 'pending'" in predicate
            assert "started_at IS NOT NULL" in predicate

            # 2. The reaper's UPDATE plan uses the index. Both statements run in this
            # connection's implicit (the test's own) transaction; SET LOCAL keeps the
            # planner setting from leaking past it.
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute(
                "EXPLAIN " + statement,
                (datetime(2000, 1, 1, tzinfo=timezone.utc),),
            )
            plan = "\n".join(row[0] for row in cur.fetchall())
            assert INDEX_NAME in plan, f"plan does not use {INDEX_NAME}:\n{plan}"
    finally:
        conn.close()
