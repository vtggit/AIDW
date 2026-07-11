"""Retention sweep executor (governance #80) — the run state machine + the DELETE semantics.

Every test drives the REAL stack: policies via the API, seeds via SQL against the test DB, the
sweep via POST /api/retention-policies/{id}/sweep, and assertions on both the run row (the audit
spine) and the swept table (observable state). Failures land ON the run — never a 5xx."""

import uuid
from datetime import datetime, timedelta, timezone


def _seed(table, rows):
    """INSERT (id, name, created_at[, dataset_id]) rows directly into the test DB."""
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        for r in rows:
            cols = ["id", "name", "created_at", "updated_at"]
            params = [r["id"], r.get("name", r["id"]), r["created_at"], r["created_at"]]
            for extra in ("dataset_id", "status"):
                if extra in r:
                    cols.append(extra)
                    params.append(r[extra])
            cur.execute(
                'INSERT INTO "%s" (%s) VALUES (%s)'
                % (table, ", ".join(cols), ", ".join(["%s"] * len(cols))),
                params,
            )


def _ids(table):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute('SELECT id FROM "%s"' % table)
        return {r["id"] for r in cur.fetchall()}       # RealDictCursor rows


def _mk_policy(client, admin_headers, **fields):
    body = {"name": "policy-%s" % uuid.uuid4().hex[:8], **fields}
    resp = client.post("/api/retention-policies", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _sweep(client, admin_headers, policy_id):
    return client.post(
        "/api/retention-policies/%s/sweep" % policy_id, headers=admin_headers
    )


NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=90)
FRESH = NOW - timedelta(days=1)


def test_class_scoped_purge_deletes_only_past_cutoff(client, admin_headers):
    pid = _mk_policy(client, admin_headers, table_class="connection_tests", action="purge",
                     scope="class", retention_period_days=30, is_enabled=True)
    old1, old2, fresh = ("ct-%s" % uuid.uuid4().hex[:8] for _ in range(3))
    _seed("connection_tests", [
        {"id": old1, "created_at": OLD}, {"id": old2, "created_at": OLD},
        {"id": fresh, "created_at": FRESH},
    ])
    r = _sweep(client, admin_headers, pid)
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "succeeded"
    assert run["records_purged"] == 2 and run["records_anonymized"] == 0
    remaining = _ids("connection_tests")
    assert fresh in remaining and old1 not in remaining and old2 not in remaining
    # idempotent: a second sweep finds nothing below the cutoff
    again = _sweep(client, admin_headers, pid).json()
    assert again["status"] == "succeeded" and again["records_purged"] == 0


def test_dataset_scoped_purge_touches_only_that_dataset(client, admin_headers):
    ds_a = client.post("/api/datasets", json={"name": "sweep-a"}, headers=admin_headers)
    ds_b = client.post("/api/datasets", json={"name": "sweep-b"}, headers=admin_headers)
    assert ds_a.status_code == 201 and ds_b.status_code == 201
    a, b = ds_a.json()["id"], ds_b.json()["id"]
    pid = _mk_policy(client, admin_headers, table_class="ingested_records", action="purge",
                     scope="dataset", dataset_id=a, retention_period_days=30, is_enabled=True)
    old_a, old_b, fresh_a = ("ir-%s" % uuid.uuid4().hex[:8] for _ in range(3))
    _seed("ingested_records", [
        {"id": old_a, "created_at": OLD, "dataset_id": a},
        {"id": old_b, "created_at": OLD, "dataset_id": b},
        {"id": fresh_a, "created_at": FRESH, "dataset_id": a},
    ])
    run = _sweep(client, admin_headers, pid).json()
    assert run["status"] == "succeeded" and run["records_purged"] == 1
    remaining = _ids("ingested_records")
    assert old_a not in remaining                    # A's old row purged
    assert old_b in remaining and fresh_a in remaining  # other dataset + fresh row kept


def test_disabled_policy_is_a_recorded_noop(client, admin_headers):
    pid = _mk_policy(client, admin_headers, table_class="runs", action="purge",
                     scope="class", retention_period_days=30, is_enabled=False)
    doomed = "ct-%s" % uuid.uuid4().hex[:8]
    _seed("connection_tests", [{"id": doomed, "created_at": OLD}])
    run = _sweep(client, admin_headers, pid).json()
    assert run["status"] == "succeeded" and run["records_purged"] == 0
    assert doomed in _ids("connection_tests")        # nothing deleted
    # free the runs class-wide slot (PR#109 partial-unique) for the lifecycle-guard test
    client.delete("/api/retention-policies/%s" % pid, headers=admin_headers)


def test_sweep_never_deletes_queued_or_inflight_runs(client, admin_headers):
    # `runs` is ALSO the ingest worker's live queue: a pending row IS queued work and a running
    # row is in-flight evidence — retention ages out TERMINAL rows only
    pid = _mk_policy(client, admin_headers, table_class="runs", action="purge",
                     scope="class", retention_period_days=30, is_enabled=True)
    old_pending, old_running, old_done = ("run-%s" % uuid.uuid4().hex[:8] for _ in range(3))
    _seed("runs", [
        {"id": old_pending, "created_at": OLD, "status": "pending"},
        {"id": old_running, "created_at": OLD, "status": "running"},
        {"id": old_done, "created_at": OLD, "status": "succeeded"},
    ])
    run = _sweep(client, admin_headers, pid).json()
    assert run["status"] == "succeeded" and run["records_purged"] == 1
    remaining = _ids("runs")
    assert old_done not in remaining                 # terminal row aged out
    assert old_pending in remaining and old_running in remaining  # live work untouched
    client.delete("/api/retention-policies/%s" % pid, headers=admin_headers)


def test_anonymize_fails_closed_on_the_run(client, admin_headers):
    pid = _mk_policy(client, admin_headers, table_class="discovery_runs", action="anonymize",
                     scope="class", retention_period_days=30, is_enabled=True)
    run = _sweep(client, admin_headers, pid).json()
    assert run["status"] == "failed"                 # recorded ON the run, not a 5xx
    assert run["records_purged"] == 0
    # free the discovery_runs slot for the misconfigured-policy test
    client.delete("/api/retention-policies/%s" % pid, headers=admin_headers)


def test_enabled_policy_without_period_fails_closed(client, admin_headers):
    # an ENABLED policy with no retention_period_days is a misconfiguration, not a no-op —
    # a green "succeeded, 0 purged" would hide "retention never enforced" forever
    pid = _mk_policy(client, admin_headers, table_class="discovery_runs", action="purge",
                     scope="class", is_enabled=True)          # period omitted (NULL)
    run = _sweep(client, admin_headers, pid).json()
    assert run["status"] == "failed"


def test_dataset_scope_without_dataset_column_fails_closed(client, admin_headers):
    pid = _mk_policy(client, admin_headers, table_class="field_profiles", action="purge",
                     scope="dataset", retention_period_days=30, is_enabled=True)
    survivor = "ct-%s" % uuid.uuid4().hex[:8]
    _seed("connection_tests", [{"id": survivor, "created_at": OLD}])
    run = _sweep(client, admin_headers, pid).json()
    assert run["status"] == "failed"
    assert survivor in _ids("connection_tests")      # fail-closed: nothing swept


def test_unknown_policy_404s(client, admin_headers):
    r = _sweep(client, admin_headers, "no-such-policy")
    assert r.status_code == 404


def test_run_claim_is_single_shot(client, admin_headers):
    from app.retention.service import create_pending_sweep, execute_sweep

    # ingested_records CLASS-scoped: coexists with the dataset-scoped policy above (the PR#109
    # partial-unique indexes are disjoint), and every other class already has a policy here
    pid = _mk_policy(client, admin_headers, table_class="ingested_records", action="purge",
                     scope="class", retention_period_days=30, is_enabled=True)
    run = create_pending_sweep(pid)
    first = execute_sweep(run["id"])
    assert first is not None and first["status"] == "succeeded"
    assert execute_sweep(run["id"]) is None          # already claimed: exactly-one-executor
