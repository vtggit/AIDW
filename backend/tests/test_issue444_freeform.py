"""Proof for issue #444 — schedule-driven load-sequence firing.

Proves ``app.worker.scheduling.fire_due_sequences_once`` against the real
database fixtures: it fires exactly the due, enabled, cadence-bearing
sequences (one pending ``sequence_runs`` row each, ``last_fired_at``
stamped), leaves non-due and unrecognised-cadence sequences untouched, and
is idempotent within the same ``now`` (an immediate second call returns
nothing).
"""

from datetime import datetime, timedelta, timezone

import psycopg2

from app.db.connection import get_connection_params
from app.worker.scheduling import fire_due_sequences_once


def _create_sequence(name, cadence, enabled, last_fired_at):
    """Insert a load_sequences row directly and return its id."""
    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO load_sequences "
                "(id, name, schedule_cadence, schedule_enabled, last_fired_at, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), %s, %s, %s, %s, NOW(), NOW()) "
                "RETURNING id",
                (name, cadence, enabled, last_fired_at),
            )
            row = cur.fetchone()
        conn.commit()
        return row[0]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fetch_sequence(sequence_id):
    """Return the load_sequences row for a sequence id as a dict."""
    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, schedule_cadence, schedule_enabled, last_fired_at "
                "FROM load_sequences WHERE id = %s",
                (sequence_id,),
            )
            row = cur.fetchone()
        conn.commit()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "schedule_cadence": row[2],
            "schedule_enabled": row[3],
            "last_fired_at": row[4],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fetch_run(run_id):
    """Return the sequence_runs row for a run id as a dict."""
    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, sequence_id, status, triggered_by "
                "FROM sequence_runs WHERE id = %s",
                (run_id,),
            )
            row = cur.fetchone()
        conn.commit()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "sequence_id": row[2],
            "status": row[3],
            "triggered_by": row[4],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_issue444_freeform(client, admin_headers):
    # Ensure isolation by truncating the relevant tables if the global
    # clean_database fixture does not cover them.
    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE sequence_runs, load_sequences RESTART IDENTITY;"
            )
        conn.commit()
    finally:
        conn.close()

    # Sanity: the API is reachable and authenticated (uses the fixtures).
    response = client.get("/api/load-sequences", headers=admin_headers)
    assert response.status_code == 200

    now = datetime.now(timezone.utc)

    # Sequence A: hourly, enabled, never fired -> due.
    seq_a = _create_sequence("seq-a", "hourly", True, None)
    # Sequence B: hourly, enabled, fired five minutes ago -> not due.
    seq_b = _create_sequence("seq-b", "hourly", True, now - timedelta(minutes=5))
    # Sequence C: unrecognised cadence -> never fired, last_fired_at stays null.
    seq_c = _create_sequence("seq-c", "not-a-cadence", True, None)

    created = fire_due_sequences_once(now=now)

    # Exactly one run was created.
    assert len(created) == 1
    run_id = created[0]

    # The created run is pending, schedule-triggered, and points at A.
    run = _fetch_run(run_id)
    assert run is not None
    assert run["status"] == "pending"
    assert run["triggered_by"] == "schedule"
    assert run["sequence_id"] == seq_a
    assert run["name"] == "scheduled: seq-a"

    # A's last_fired_at was stamped to now.
    seq_a_after = _fetch_sequence(seq_a)
    assert seq_a_after["last_fired_at"] is not None
    assert seq_a_after["last_fired_at"].replace(tzinfo=None) == now.replace(tzinfo=None)

    # B is untouched (still five minutes before now).
    seq_b_after = _fetch_sequence(seq_b)
    assert seq_b_after["last_fired_at"] is not None
    assert seq_b_after["last_fired_at"].replace(tzinfo=None) == (
        now - timedelta(minutes=5)
    ).replace(tzinfo=None)

    # C (unrecognised cadence) was not fired; last_fired_at stays null.
    seq_c_after = _fetch_sequence(seq_c)
    assert seq_c_after["last_fired_at"] is None

    # An immediate second call with the same now fires nothing.
    assert fire_due_sequences_once(now=now) == []
