"""Proof for issue #457 — feed credential authentication dependency.

Mounts a single route that depends on ``require_feed_credential`` on a fresh
FastAPI app, seeds a ``feed_credentials`` row directly via ``get_cursor``, and
exercises every acceptance path: no credentials, valid Basic, valid X-Api-Key,
wrong key, wrong Basic username, a Bearer token (must be 401, not 500), and a
revoked credential.
"""

import base64
import hashlib
import secrets
import uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.db.connection import get_cursor
from app.feed.auth import require_feed_credential

_WWW_AUTHENTICATE = "Basic realm=" + chr(34) + "AIDW feed" + chr(34)


def _build_app() -> FastAPI:
    """Build a fresh FastAPI app with one route guarded by the feed dependency."""
    application = FastAPI()

    @application.get("/feed/ping")
    def ping(credential: dict = Depends(require_feed_credential)):
        return {"ok": True, "name": credential.get("name")}

    return application


def _seed_credential(principal: str, plaintext_key: str) -> str:
    """Insert a feed_credentials row directly and return its id."""
    credential_id = uuid.uuid4().hex
    key_hash = hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()
    key_prefix = plaintext_key[:8]
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO feed_credentials "
            "(id, name, principal, key_hash, key_prefix, revoked) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                credential_id,
                "issue457 feed",
                principal,
                key_hash,
                key_prefix,
                False,
            ),
        )
    return credential_id


def _revoke_credential(credential_id: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE feed_credentials SET revoked = %s WHERE id = %s",
            (True, credential_id),
        )


def _basic_header(principal: str, key: str) -> dict:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_issue457_freeform(admin_headers):
    principal = f"issue457-{uuid.uuid4().hex}"
    plaintext_key = secrets.token_urlsafe(32)
    credential_id = _seed_credential(principal, plaintext_key)

    app = _build_app()
    with TestClient(app) as client:
        # No credentials at all -> 401 with the WWW-Authenticate challenge.
        response = client.get("/feed/ping")
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE

        # Valid Basic principal:key -> 200.
        response = client.get(
            "/feed/ping", headers=_basic_header(principal, plaintext_key)
        )
        assert response.status_code == 200
        assert response.json()["name"] == "issue457 feed"

        # Valid X-Api-Key -> 200.
        response = client.get("/feed/ping", headers={"X-Api-Key": plaintext_key})
        assert response.status_code == 200
        assert response.json()["name"] == "issue457 feed"

        # Wrong key (Basic) -> 401.
        response = client.get(
            "/feed/ping", headers=_basic_header(principal, "not-the-right-key")
        )
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE

        # Right key but wrong Basic username -> 401.
        response = client.get(
            "/feed/ping", headers=_basic_header(f"{principal}-wrong", plaintext_key)
        )
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE

        # A Bearer token (conftest admin_headers) is not a feed credential -> 401, not 500.
        response = client.get("/feed/ping", headers=dict(admin_headers))
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE

        # Once the row is revoked, even the right key -> 401.
        _revoke_credential(credential_id)
        response = client.get(
            "/feed/ping", headers=_basic_header(principal, plaintext_key)
        )
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE
        response = client.get("/feed/ping", headers={"X-Api-Key": plaintext_key})
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE
