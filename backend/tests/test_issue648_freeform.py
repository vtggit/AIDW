"""Issue #648 — the stranded-scheduled reaper must also see runs whose status is NULL.

Proves, end to end:
1. (AC-1) reap_stranded_scheduled's UPDATE matches COALESCE(status, 'pending') =
   'pending' and keeps every other part of the statement unchanged;
2. (AC-2) migration 0104 recreated idx_sequence_runs_stranded_scheduled under the
   same name with the aligned predicate, and the alembic chain keeps exactly one
   head;
3. (AC-3) a stranded scheduled run with a NULL status is reaped, while a NULL-status
   run whose updated_at is recent is not;
4. (AC-4) the index-predicate normalization used by the index tests strips
   PostgreSQL's cast syntax (e.g. ::character varying), not only ::text, so the
   COALESCE-based predicate compares as bare text.
"""

import ast
import pathlib
import re

import psycopg2
import pytest

INDEX_NAME = "idx_sequence_runs_stranded_scheduled"
_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_LOOP_PY = _BACKEND / "app" / "worker" / "loop.py"


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


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_issue648_freeform():
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    # The normalization under test (AC-4) lives in the index test module.
    from test_idx_sequence_runs_updated_at_partial import _canonicalize

    from app.db.connection import get_connection_params
    from app.worker import loop

    # ------------------------------------------------------------------
    # AC-1: the reaper UPDATE matches COALESCE(status, 'pending') = 'pending'
    # and every other part of the statement is unchanged
    # ------------------------------------------------------------------
    statement = _reaper_update_statement()
    assert "UPDATE sequence_runs SET started_at = NULL, updated_at = NOW()" in statement
    assert "triggered_by = 'schedule'" in statement
    assert "COALESCE(status, 'pending') = 'pending'" in statement
    assert "started_at IS NOT NULL" in statement
    assert "updated_at <" in statement
    # the old bare equality is gone (not merely supplemented), and started_at
    # is still never compared temporally (VARCHAR(255) safety)
    assert "status = 'pending'" not in statement
    assert "started_at <" not in statement
    assert "started_at >" not in statement

    # ------------------------------------------------------------------
    # AC-2: migration 0104 — the chain has exactly one head, and the index
    # was recreated under the same name with the aligned predicate
    # ------------------------------------------------------------------
    config = AlembicConfig(str(_BACKEND / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0104_align_reaper_idx_null_stat"]
    assert (
        script.get_revision("0104_align_reaper_idx_null_stat").down_revision
        == "0103_add_idx_sequence_runs_reap"
    )

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            # AC-3 setup: one stranded NULL-status run (stale updated_at), one
            # fresh NULL-status run, and one stranded non-pending run that must
            # stay untouched.
            cur.execute(
                "INSERT INTO sequence_runs "
                "(id, name, status, started_at, updated_at, triggered_by) "
                "VALUES (%s, %s, NULL, %s, NOW() - INTERVAL '120 seconds', 'schedule')",
                (
                    "run-null-stranded",
                    "null status, stranded",
                    "2000-01-01T00:00:00+00:00",
                ),
            )
            cur.execute(
                "INSERT INTO sequence_runs "
                "(id, name, status, started_at, updated_at, triggered_by) "
                "VALUES (%s, %s, NULL, %s, NOW(), 'schedule')",
                ("run-null-recent", "null status, fresh", "2000-01-01T00:00:00+00:00"),
            )
            cur.execute(
                "INSERT INTO sequence_runs "
                "(id, name, status, started_at, updated_at, triggered_by) "
                "VALUES (%s, %s, 'failed', %s, NOW() - INTERVAL '120 seconds', 'schedule')",
                (
                    "run-failed-stranded",
                    "failed, stranded",
                    "2000-01-01T00:00:00+00:00",
                ),
            )
        conn.commit()

        # AC-3: the reaper (real query, real DB) clears the claim marker on the
        # stranded NULL-status run only.
        reaped = loop.reap_stranded_scheduled(max_age_seconds=60)
        assert reaped == 1

        with conn.cursor() as cur:
            cur.execute(
                "SELECT started_at, status FROM sequence_runs WHERE id = %s",
                ("run-null-stranded",),
            )
            stranded_started, stranded_status = cur.fetchone()
            cur.execute(
                "SELECT started_at FROM sequence_runs WHERE id = %s",
                ("run-null-recent",),
            )
            recent_started = cur.fetchone()[0]
            cur.execute(
                "SELECT started_at FROM sequence_runs WHERE id = %s",
                ("run-failed-stranded",),
            )
            failed_started = cur.fetchone()[0]

            # AC-2: the recreation landed in the migrated test database.
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
            assert not re.search(r"\bUNIQUE\b", indexdef, re.IGNORECASE)
            assert re.search(r"\bON\s+\S*sequence_runs\b", indexdef)
            assert "(updated_at)" in indexdef

    finally:
        conn.close()

    # AC-3 assertions: the NULL-status stranded run was reaped, the fresh
    # NULL-status run and the failed run were left alone.
    assert stranded_started is None
    assert stranded_status is None
    assert recent_started == "2000-01-01T00:00:00+00:00"
    assert failed_started == "2000-01-01T00:00:00+00:00"

    # ------------------------------------------------------------------
    # AC-2 predicate + AC-4 normalization: the stored predicate compares as
    # bare text once the cast syntax is stripped
    # ------------------------------------------------------------------
    predicate = _canonicalize(indexdef)
    assert "triggered_by = 'schedule'" in predicate
    assert "COALESCE status 'pending' = 'pending'" in predicate
    assert "started_at IS NOT NULL" in predicate
    assert "status = 'pending'" not in predicate

    # AC-4: the normalization must strip ::character varying (and friends), not
    # only ::text — proven on a synthetic indexdef shaped exactly like
    # PostgreSQL's rendering of the new predicate.
    synthetic = (
        "CREATE INDEX idx_sequence_runs_stranded_scheduled ON public.sequence_runs "
        "USING btree (updated_at) WHERE ((triggered_by = 'schedule'::text) "
        "AND ((COALESCE(status, 'pending'::character varying))::text = 'pending'::text) "
        "AND (started_at IS NOT NULL))"
    )
    normalized = _canonicalize(synthetic)
    assert "::" not in normalized
    assert "COALESCE status 'pending' = 'pending'" in normalized
