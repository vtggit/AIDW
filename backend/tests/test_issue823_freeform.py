"""Proving test for issue #823 — fixed-shape, message-free ``error_detail``.

Proves every acceptance criterion against the test database:

* ``safe_error_detail`` for a REAL psycopg2 integrity error raised in this
  test (a foreign-key violation whose DETAIL line names
  ``jane.erasure@example.test``): the result names the exception class and the
  SQLSTATE code, and contains none of the value, "DETAIL", or "Key (";
* ``safe_error_detail`` for a plain ``ValueError("jane.erasure@example.test")``
  is exactly ``"ValueError"`` — without the value;
* an exception object whose ``__str__`` raises: no exception escapes;
* a retention sweep made to fail by the test with an error carrying that
  value: the run is ``failed``, and its ``error_detail`` read back through
  ``GET /api/retention-runs/{id}`` does not contain the value;
* a deletion request whose execution is made to fail the same way: back to
  ``verifying`` with attempts increased by one, and its ``error_detail``
  without the value.
"""

import logging
import uuid

import psycopg2

from app.db.connection import get_cursor
from app.governance.safe_error import safe_error_detail

PII_VALUE = "jane.erasure@example.test"


def _real_integrity_error() -> psycopg2.IntegrityError:
    """Trigger a REAL psycopg2 integrity error in the test database and return it.

    The probe is an ``ingested_records`` insert whose ``dataset_id`` is
    ``PII_VALUE``: the value fits the FK column but matches no dataset, so the
    database itself raises the foreign-key violation (SQLSTATE 23503) whose
    DETAIL line names the value. The insert rolls back — nothing persists.
    """
    with get_cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO ingested_records "
                "(id, name, dataset_id, business_key, op) "
                "VALUES (%s, %s, %s, %s, 'insert')",
                (uuid.uuid4().hex, "fk probe", PII_VALUE, "probe-key"),
            )
        except psycopg2.IntegrityError as exc:
            return exc
    raise AssertionError("expected an integrity error from the dangling FK insert")


def test_issue823_freeform(client, admin_headers, monkeypatch, caplog):
    # ------------------------------------------------------------------
    # 1. A real psycopg2 integrity error raised in this test, whose message
    #    (DETAIL line) names PII_VALUE: the detail names the class and the
    #    SQLSTATE — never the value, "DETAIL", or "Key (".
    # ------------------------------------------------------------------
    exc = _real_integrity_error()
    assert isinstance(exc, psycopg2.IntegrityError)
    assert exc.pgcode == "23503"
    assert PII_VALUE in str(exc)  # sanity: the message really carries the value
    detail = safe_error_detail(exc)
    assert detail == f"{type(exc).__name__} (SQLSTATE {exc.pgcode})"
    assert type(exc).__name__ in detail
    assert "SQLSTATE" in detail and exc.pgcode in detail
    assert PII_VALUE not in detail
    assert "DETAIL" not in detail
    assert "Key (" not in detail

    # ------------------------------------------------------------------
    # 2. A plain ValueError whose message is the value: the class name alone,
    #    without the value.
    # ------------------------------------------------------------------
    assert safe_error_detail(ValueError(PII_VALUE)) == "ValueError"

    # ------------------------------------------------------------------
    # 3. An exception whose __str__ raises: nothing escapes.
    # ------------------------------------------------------------------
    class _Unreadable(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("the message must never be read")

    assert safe_error_detail(_Unreadable()) == "_Unreadable"

    # ------------------------------------------------------------------
    # 4. A retention sweep made to fail by the test with an error carrying
    #    the value: the run is failed, and the error_detail read back through
    #    GET /api/retention-runs/{id} does not contain the value.
    # ------------------------------------------------------------------
    from app.retention import service as retention_service

    created = client.post(
        "/api/retention-policies",
        json={
            "name": f"pii sweep {uuid.uuid4().hex[:8]}",
            "table_class": "connection_tests",
            "action": "purge",
            "scope": "class",
            "retention_period_days": 30,
            "is_enabled": True,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    policy_id = created.json()["id"]
    run = retention_service.create_pending_sweep(policy_id)

    def _boom(_run_id):
        raise exc  # the real integrity error: its message names PII_VALUE

    monkeypatch.setattr(retention_service, "_do_sweep", _boom)
    finished = retention_service.execute_sweep(run["id"])
    assert finished is not None and finished["status"] == "failed"

    got = client.get(f"/api/retention-runs/{run['id']}", headers=admin_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "failed"
    assert body["error_detail"] == detail  # class + SQLSTATE only
    assert PII_VALUE not in body["error_detail"]
    assert "DETAIL" not in body["error_detail"]
    assert "Key (" not in body["error_detail"]

    # ------------------------------------------------------------------
    # 5. A deletion request whose execution is made to fail the same way:
    #    back to verifying with attempts increased by one, and the
    #    error_detail without the value.
    # ------------------------------------------------------------------
    from app.governance import executor as erasure_executor

    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", "issue823-test-pepper")
    ds = client.post(
        "/api/datasets",
        json={"name": f"pii erasure {uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert ds.status_code == 201, ds.text
    dataset_id = ds.json()["id"]
    request_id = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO ingested_records "
            "(id, name, dataset_id, business_key, op) "
            "VALUES (%s, %s, %s, %s, 'insert')",
            (uuid.uuid4().hex, "subject row", dataset_id, PII_VALUE),
        )
        cur.execute(
            "INSERT INTO deletion_requests "
            "(id, name, subject_key, status, dataset_id, attempts, verified_by) "
            "VALUES (%s, %s, %s, 'verifying', %s, 0, 'admin-a')",
            (request_id, f"erase {PII_VALUE}", PII_VALUE, dataset_id),
        )

    def _audit_boom(*_args, **_kwargs):
        raise exc  # mid-transaction, the same error carrying the value

    monkeypatch.setattr(erasure_executor, "record_audit", _audit_boom)
    assert erasure_executor.execute_deletion(request_id) is False

    got = client.get(f"/api/deletion-requests/{request_id}", headers=admin_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "verifying"
    assert body["attempts"] == 1  # 0 + 1: retry-not-fail requeue
    assert body["error_detail"] == detail  # class + SQLSTATE only
    assert PII_VALUE not in body["error_detail"]
    assert "DETAIL" not in body["error_detail"]
    assert "Key (" not in body["error_detail"]

    # the failed erasure rolled back whole: the subject's row is still there
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM ingested_records "
            "WHERE dataset_id = %s AND business_key = %s",
            (dataset_id, PII_VALUE),
        )
        assert cur.fetchone()["n"] == 1

    # ------------------------------------------------------------------
    # 6. Logs unchanged: the FULL exception — message, DETAIL line and
    #    traceback — still reaches the server log on the erasure failure
    #    path (issue #823 keeps the audit row safe, not the operator
    #    blind).
    # ------------------------------------------------------------------
    erasure_logs = [
        record
        for record in caplog.records
        if record.name == "app.governance.executor" and record.levelno >= logging.ERROR
    ]
    assert erasure_logs, "the erasure failure path must log the full exception"
    rendered = "\n".join(logging.Formatter().format(record) for record in erasure_logs)
    assert PII_VALUE in rendered  # the full exception: the message names the value
    assert "Traceback" in rendered  # ...with its traceback
