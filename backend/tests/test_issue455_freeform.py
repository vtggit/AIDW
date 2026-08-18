"""Issue #455 — feed credential key rotation.

Proves that POST /api/feed-credentials/{entity_id}/rotate (admin-only, declared
before the /{entity_id} routes) generates a fresh key, persists only its SHA-256
digest and 8-char prefix through the existing repository update path, and returns
the plaintext key exactly once.
"""

import hashlib

from app.repositories.feed_credentials_postgres_repository import (
    FeedCredentialPostgresRepository,
)


def test_issue455_freeform(client, admin_headers, user_headers, monkeypatch):
    # Create a credential via the API as admin.
    create_resp = client.post(
        "/api/feed-credentials",
        json={"name": "acme-feed", "principal": "acme:svc"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    entity_id = create_resp.json()["id"]

    # Rotate on an unknown id -> 404.
    missing = client.post(
        "/api/feed-credentials/does-not-exist/rotate",
        headers=admin_headers,
    )
    assert missing.status_code == 404, missing.text

    # Rotate with non-admin headers -> 403.
    forbidden = client.post(
        f"/api/feed-credentials/{entity_id}/rotate",
        headers=user_headers,
    )
    assert forbidden.status_code == 403, forbidden.text

    # Monkeypatch the repository update with a recorder that captures `data`
    # and delegates to the original captured BEFORE patching.
    original_update = FeedCredentialPostgresRepository.update
    calls = []

    def recording_update(self, entity_id, data):
        calls.append(data)
        return original_update(self, entity_id, data)

    monkeypatch.setattr(FeedCredentialPostgresRepository, "update", recording_update)

    # Rotate as admin.
    rotate_resp = client.post(
        f"/api/feed-credentials/{entity_id}/rotate",
        headers=admin_headers,
    )
    assert rotate_resp.status_code == 200, rotate_resp.text
    body = rotate_resp.json()

    key = body["key"]
    assert len(key) == 43, f"expected 43-char key, got {len(key)}"
    assert body["key_prefix"] == key[:8]

    # The recorder ran exactly once, with key_hash + key_prefix and no plaintext.
    assert len(calls) == 1, f"expected one update call, got {len(calls)}"
    data = calls[0]
    assert "key_hash" in data
    assert "key_prefix" in data
    assert data["key_prefix"] == key[:8]
    assert key not in data.values(), "plaintext key must not be persisted"

    # A subsequent GET returns the stored hash and no plaintext key field.
    get_resp = client.get(
        f"/api/feed-credentials/{entity_id}",
        headers=admin_headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    stored = get_resp.json()
    assert stored["key_hash"] == hashlib.sha256(key.encode()).hexdigest()
    assert "key" not in stored
