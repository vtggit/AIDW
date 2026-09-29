"""Index test (issue #632, predicate realigned by #648) — idx_sequence_runs_stranded_scheduled,
the partial index on sequence_runs(updated_at) created by migration 0103 and recreated by
migration 0104, exists with the reaper's predicate:
triggered_by = 'schedule' AND COALESCE(status, 'pending') = 'pending'
AND started_at IS NOT NULL."""

import re

import psycopg2
import pytest

INDEX_NAME = "idx_sequence_runs_stranded_scheduled"


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


def _normalized_indexdef(cur) -> str:
    """Return the whitespace-normalized pg_indexes indexdef for the index on sequence_runs."""
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
    return re.sub(r"\s+", " ", rows[0][0])


@pytest.mark.usefixtures("test_database", "test_env_setup")
def test_idx_sequence_runs_updated_at_partial_exists():
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            indexdef = _normalized_indexdef(cur)
            # Plain (non-unique) partial index on sequence_runs, key column updated_at ...
            assert not re.search(r"\bUNIQUE\b", indexdef, re.IGNORECASE)
            assert re.search(r"\bON\s+\S*sequence_runs\b", indexdef)
            assert "(updated_at)" in indexdef
            # ... whose predicate matches the reaper's UPDATE filter.
            predicate = _canonicalize(indexdef)
            assert "triggered_by = 'schedule'" in predicate
            # #648: NULL status means pending (COALESCE), no bare equality
            assert "COALESCE status 'pending' = 'pending'" in predicate
            assert "started_at IS NOT NULL" in predicate
    finally:
        conn.close()
