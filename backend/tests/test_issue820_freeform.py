"""Proving test for issue #820 — feed credential ``last_used_at``.

Proves every acceptance criterion against the test database:

* a new key is listed with ``last_used_at`` null;
* one feed request with that key through ``X-Api-Key`` sets ``last_used_at``
  to within a few seconds of the request, with exactly one UPDATE statement,
  and the persisted value equals the value the API reports;
* a second request at once leaves ``last_used_at`` unchanged and makes no
  UPDATE statement at all — proven by counting UPDATEs on the table rather
  than by comparing timestamps alone, so a per-request write cannot pass;
* a request after the stored time has been moved back 61 seconds moves
  ``last_used_at`` forward again (exactly one UPDATE statement);
* the same holds through Basic authentication (exactly one UPDATE
  statement);
* a request with a wrong key and one with a revoked key get 401 and no
  row's ``last_used_at`` changes and no UPDATE statement is made;
* a write made to fail by the test (an injected Postgres trigger) still
  answers 200, leaves ``last_used_at`` unchanged, makes no UPDATE
  statement, and is logged;
* ``last_used_at`` in a create or update request body is rejected with
  422 — the 422 is about ``last_used_at`` itself, not a missing principal —
  and ``key_hash`` is absent from every response;
* the 0105 migration upgrades and downgrades cleanly.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db.connection import get_cursor

_WWW_AUTHENTICATE = "Basic realm=" + chr(34) + "AIDW feed" + chr(34)

# DB clock vs. app clock skew tolerance: "within a few seconds".
_CLOCK_TOLERANCE = timedelta(seconds=10)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_iso(value) -> datetime:
    """Parse an ISO 8601 string (or pass through a datetime from the DB)."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(credential_id: str) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, last_used_at FROM feed_credentials WHERE id = %s",
            (credential_id,),
        )
        fetched = cur.fetchone()
    return dict(fetched) if fetched else {}


def _last_used(credential_id: str):
    return _row(credential_id).get("last_used_at")


def _move_back(credential_id: str) -> None:
    """Move the stored last_used_at back 61 seconds (past the 60s throttle)."""
    with get_cursor() as cur:
        cur.execute(
            "UPDATE feed_credentials "
            "SET last_used_at = last_used_at - INTERVAL '61 seconds' "
            "WHERE id = %s",
            (credential_id,),
        )


def _snapshot() -> dict:
    """Every feed_credentials row's last_used_at, keyed by id."""
    with get_cursor() as cur:
        cur.execute("SELECT id, last_used_at FROM feed_credentials ORDER BY id")
        return {row["id"]: row["last_used_at"] for row in cur.fetchall()}


def _columns() -> set:
    with get_cursor() as cur:
        cur.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'feed_credentials' AND table_schema = 'public'"
        )
        return {row["column_name"] for row in cur.fetchall()}


def _is_nullable(column: str) -> bool:
    with get_cursor() as cur:
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'feed_credentials' AND table_schema = 'public' "
            "AND column_name = %s",
            (column,),
        )
        row = cur.fetchone()
    return row is not None and row["is_nullable"] == "YES"


def _install_update_counter() -> None:
    """Count UPDATE statements on feed_credentials via a BEFORE UPDATE trigger.

    Idempotent: a crashed run can leave the objects behind (the test
    database survives across pytest invocations), so the trigger is dropped
    and the function/table reset before being (re)created.
    """
    with get_cursor() as cur:
        cur.execute("DROP TRIGGER IF EXISTS issue820_count_updates ON feed_credentials")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS issue820_update_count "
            "(n INTEGER NOT NULL DEFAULT 0)"
        )
        cur.execute(
            "CREATE OR REPLACE FUNCTION issue820_count_updates() "
            "RETURNS trigger AS $$ BEGIN "
            "UPDATE issue820_update_count SET n = n + 1; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        cur.execute(
            "CREATE TRIGGER issue820_count_updates BEFORE UPDATE "
            "ON feed_credentials FOR EACH ROW "
            "EXECUTE FUNCTION issue820_count_updates()"
        )
        cur.execute("DELETE FROM issue820_update_count")
        cur.execute("INSERT INTO issue820_update_count (n) VALUES (0)")


def _reset_update_counter() -> None:
    with get_cursor() as cur:
        cur.execute("UPDATE issue820_update_count SET n = 0")


def _update_count() -> int:
    with get_cursor() as cur:
        cur.execute("SELECT n FROM issue820_update_count")
        row = cur.fetchone()
    return row["n"] if row else 0


def _drop_update_counter() -> None:
    with get_cursor() as cur:
        cur.execute("DROP TRIGGER IF EXISTS issue820_count_updates ON feed_credentials")
        cur.execute("DROP FUNCTION IF EXISTS issue820_count_updates()")
        cur.execute("DROP TABLE IF EXISTS issue820_update_count")


def _alembic(*args: str) -> None:
    """Run an alembic command against the test database."""
    backend_dir = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DB_NAME": "aicrm_test_db"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_dir / "alembic.ini"),
            *args,
        ],
        cwd=backend_dir,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_issue820_freeform(client, admin_headers, caplog):
    principal = "issue820-svc"
    plaintext_key = secrets.token_urlsafe(32)

    # ------------------------------------------------------------------
    # Criterion: a new key is listed with last_used_at null (and key_hash
    # is absent from the create response).
    # ------------------------------------------------------------------
    created = client.post(
        "/api/feed-credentials",
        json={
            "name": "issue820 feed",
            "principal": principal,
            "key_hash": _sha256_hex(plaintext_key),
            "key_prefix": plaintext_key[:8],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    entity_id = body["id"]
    assert "key_hash" not in body
    assert body["last_used_at"] is None

    listing = client.get("/api/feed-credentials", headers=admin_headers)
    assert listing.status_code == 200
    listed_row = next(item for item in listing.json() if item["id"] == entity_id)
    assert "key_hash" not in listed_row
    assert listed_row["last_used_at"] is None

    detail = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert "key_hash" not in detail.json()
    assert detail.json()["last_used_at"] is None

    # ------------------------------------------------------------------
    # Criterion: one feed request with the key through X-Api-Key sets
    # last_used_at, within a few seconds of the request.
    # ------------------------------------------------------------------
    _install_update_counter()
    before = _now()
    response = client.get("/api/feed/v4", headers={"X-Api-Key": plaintext_key})
    after = _now()
    assert response.status_code == 200, response.text
    assert _update_count() == 1  # a first use writes exactly once

    detail = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert detail.status_code == 200
    first_value = detail.json()["last_used_at"]
    assert first_value is not None
    first_time = _parse_iso(first_value)  # ISO 8601
    assert before - _CLOCK_TOLERANCE <= first_time <= after + _CLOCK_TOLERANCE
    # persisted, not just projected: the DB row carries a value within a few
    # seconds of the request, and the API reports exactly that value
    persisted = _last_used(entity_id)
    assert persisted is not None
    persisted_time = _parse_iso(persisted)
    assert before - _CLOCK_TOLERANCE <= persisted_time <= after + _CLOCK_TOLERANCE
    assert _parse_iso(first_value) == persisted_time

    # ------------------------------------------------------------------
    # Criterion: a second request at once leaves last_used_at unchanged
    # (the conditional UPDATE fires at most once a minute per key).
    # ------------------------------------------------------------------
    _reset_update_counter()
    response = client.get("/api/feed/v4", headers={"X-Api-Key": plaintext_key})
    assert response.status_code == 200, response.text
    # within the 60s window no write may happen at all — proven by the
    # UPDATE count, so a per-request write cannot pass even when its
    # timestamp would compare equal
    assert _update_count() == 0
    detail = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert detail.json()["last_used_at"] == first_value

    # ------------------------------------------------------------------
    # Criterion: after the stored time has been moved back 61 seconds, a
    # request moves last_used_at forward again — first through X-Api-Key.
    # ------------------------------------------------------------------
    _move_back(entity_id)
    moved = _last_used(entity_id)
    _reset_update_counter()
    response = client.get("/api/feed/v4", headers={"X-Api-Key": plaintext_key})
    assert response.status_code == 200, response.text
    assert _update_count() == 1  # past the window the write is allowed again
    detail = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    moved_value = detail.json()["last_used_at"]
    assert _parse_iso(moved_value) > _parse_iso(moved)
    request_time = _now()
    assert abs(_parse_iso(moved_value) - request_time) <= _CLOCK_TOLERANCE
    # the persisted value is the one the API reports
    assert _parse_iso(moved_value) == _last_used(entity_id)

    # ------------------------------------------------------------------
    # Criterion: the same through Basic authentication.
    # ------------------------------------------------------------------
    _move_back(entity_id)
    moved = _last_used(entity_id)
    _reset_update_counter()
    basic_token = base64.b64encode(f"{principal}:{plaintext_key}".encode()).decode()
    before = _now()
    response = client.get(
        "/api/feed/v4", headers={"Authorization": f"Basic {basic_token}"}
    )
    after = _now()
    assert response.status_code == 200, response.text
    assert _update_count() == 1  # a Basic-authenticated use writes exactly once
    detail = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    basic_value = detail.json()["last_used_at"]
    assert _parse_iso(basic_value) > _parse_iso(moved)
    # persisted, not just projected: within a few seconds of the request,
    # and equal to the value the API reports
    persisted_basic = _last_used(entity_id)
    assert persisted_basic is not None
    assert (
        before - _CLOCK_TOLERANCE
        <= _parse_iso(persisted_basic)
        <= after + _CLOCK_TOLERANCE
    )
    assert _parse_iso(basic_value) == persisted_basic

    # ------------------------------------------------------------------
    # Criterion: a wrong key gets 401 and no row's last_used_at changes.
    # ------------------------------------------------------------------
    snapshot = _snapshot()
    _reset_update_counter()
    response = client.get(
        "/api/feed/v4", headers={"X-Api-Key": "issue820-not-a-real-key"}
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE
    assert _snapshot() == snapshot
    assert _update_count() == 0  # a failed authentication never writes

    # ------------------------------------------------------------------
    # Criterion: a revoked key gets 401 and no row's last_used_at changes.
    # ------------------------------------------------------------------
    revoked = client.put(
        f"/api/feed-credentials/{entity_id}",
        json={"revoked": True},
        headers=admin_headers,
    )
    assert revoked.status_code == 200, revoked.text
    snapshot = _snapshot()
    _reset_update_counter()
    response = client.get("/api/feed/v4", headers={"X-Api-Key": plaintext_key})
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE
    assert _snapshot() == snapshot
    assert _update_count() == 0  # a revoked credential never writes
    unrevoked = client.put(
        f"/api/feed-credentials/{entity_id}",
        json={"revoked": False},
        headers=admin_headers,
    )
    assert unrevoked.status_code == 200, unrevoked.text

    # ------------------------------------------------------------------
    # Criterion: a write made to fail by the test — the request still
    # answers 200, last_used_at is unchanged, and the failure is logged.
    # ------------------------------------------------------------------
    _move_back(entity_id)
    moved = _last_used(entity_id)
    with get_cursor() as cur:
        cur.execute(
            "CREATE FUNCTION issue820_fail_feed_update() RETURNS trigger "
            "AS $$ BEGIN "
            "RAISE EXCEPTION 'injected last_used_at write failure (issue820)'; "
            "END; $$ LANGUAGE plpgsql"
        )
        cur.execute(
            "CREATE TRIGGER issue820_fail_feed_update BEFORE UPDATE "
            "ON feed_credentials FOR EACH ROW "
            "EXECUTE FUNCTION issue820_fail_feed_update()"
        )
    _reset_update_counter()
    try:
        with caplog.at_level(logging.ERROR, logger="app.feed.auth"):
            response = client.get("/api/feed/v4", headers={"X-Api-Key": plaintext_key})
        assert response.status_code == 200, response.text
        assert _update_count() == 0  # the failed write left no write behind
        assert _last_used(entity_id) == moved
        assert any(
            record.levelno >= logging.ERROR and "last_used_at" in record.getMessage()
            for record in caplog.records
        )
    finally:
        with get_cursor() as cur:
            cur.execute(
                "DROP TRIGGER IF EXISTS issue820_fail_feed_update ON feed_credentials"
            )
            cur.execute("DROP FUNCTION IF EXISTS issue820_fail_feed_update()")

    # ------------------------------------------------------------------
    # Criterion: last_used_at in a create or update request body is
    # rejected with 422 (and cannot be set); key_hash stays absent.
    # ------------------------------------------------------------------
    guard = client.post(
        "/api/feed-credentials",
        json={"name": "issue820 guard", "principal": "issue820-guard"},
        headers=admin_headers,
    )
    assert guard.status_code == 201, guard.text
    guard_id = guard.json()["id"]
    assert guard.json()["last_used_at"] is None

    # A principal is supplied so a missing-principal error cannot confound
    # the check: the 422 must come from the forbidden last_used_at field.
    bad_create = client.post(
        "/api/feed-credentials",
        json={
            "name": "issue820 bad",
            "principal": "issue820-bad",
            "last_used_at": "2020-01-01T00:00:00+00:00",
        },
        headers=admin_headers,
    )
    assert bad_create.status_code == 422
    assert "last_used_at" in json.dumps(bad_create.json())

    bad_update = client.put(
        f"/api/feed-credentials/{guard_id}",
        json={"last_used_at": "2020-01-01T00:00:00+00:00"},
        headers=admin_headers,
    )
    assert bad_update.status_code == 422

    guard_detail = client.get(
        f"/api/feed-credentials/{guard_id}", headers=admin_headers
    )
    assert guard_detail.status_code == 200
    assert guard_detail.json()["last_used_at"] is None

    # ------------------------------------------------------------------
    # Criterion (AC-3): list, detail, and rotate responses carry
    # last_used_at (ISO 8601 string or null) and never key_hash.
    # ------------------------------------------------------------------
    listing = client.get("/api/feed-credentials", headers=admin_headers)
    assert listing.status_code == 200
    for item in listing.json():
        assert "key_hash" not in item
        assert "last_used_at" in item
    listed_main = next(item for item in listing.json() if item["id"] == entity_id)
    assert listed_main["last_used_at"] is not None
    _parse_iso(listed_main["last_used_at"])  # ISO 8601

    rotated = client.post(
        f"/api/feed-credentials/{guard_id}/rotate", headers=admin_headers
    )
    assert rotated.status_code == 200, rotated.text
    rotated_body = rotated.json()
    assert "key_hash" not in rotated_body
    assert rotated_body["key"]
    assert rotated_body["last_used_at"] is None

    detail = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert "key_hash" not in detail.json()
    assert detail.json()["last_used_at"] is not None

    # ------------------------------------------------------------------
    # Criterion: the 0105 migration downgrades and upgrades cleanly.
    # ------------------------------------------------------------------
    _alembic("downgrade", "-1")
    try:
        assert "last_used_at" not in _columns()
    finally:
        _alembic("upgrade", "head")
    assert "last_used_at" in _columns()
    assert _is_nullable("last_used_at")

    _drop_update_counter()
