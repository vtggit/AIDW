"""Issue #513 — freeform acceptance proof.

Proves the three #513 acceptance criteria against the live API:

1. Non-admin callers cannot obtain ``key_hash`` (or any equivalent key
   material) from the feed-credentials API — list/get are open to
   authenticated users but the response returned to a non-admin contains no
   ``key_hash`` (admins still see the full record).
2. A valid ``X-Api-Key`` authenticates even when an unrelated (non-Basic)
   ``Authorization`` header is also present, while a valid Basic
   ``Authorization`` header still authenticates.
3. ``require_feed_credential`` never 500s on a malformed stored ``key_hash``:
   a non-ASCII stored value 401s (treated as a non-match) while other valid
   rows still authenticate.
"""

import base64
import hashlib

from app.db.connection import get_cursor


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _basic(principal: str, key: str) -> str:
    return "Basic " + base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")


def test_issue513_freeform(client, admin_headers, user_headers):
    # ------------------------------------------------------------------
    # Criterion 1 — non-admins cannot obtain key_hash from the API.
    # ------------------------------------------------------------------
    created = client.post(
        "/api/feed-credentials",
        json={
            "name": "issue513",
            "principal": "svc",
            "key_hash": "deadbeef",
            "key_prefix": "abcd1234",
            "revoked": False,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    entity_id = created.json()["id"]

    # Admins still see the full record (including key material).
    admin_get = client.get(f"/api/feed-credentials/{entity_id}", headers=admin_headers)
    assert admin_get.status_code == 200, admin_get.text
    assert admin_get.json()["key_hash"] == "deadbeef"

    # Non-admins can read the record but the response contains no key_hash.
    non_admin_get = client.get(
        f"/api/feed-credentials/{entity_id}", headers=user_headers
    )
    assert non_admin_get.status_code == 200, non_admin_get.text
    assert "key_hash" not in non_admin_get.json()

    non_admin_list = client.get("/api/feed-credentials", headers=user_headers)
    assert non_admin_list.status_code == 200, non_admin_list.text
    for item in non_admin_list.json():
        assert "key_hash" not in item

    # ------------------------------------------------------------------
    # Criterion 2 — X-Api-Key works alongside an unrelated Authorization
    # header; a valid Basic Authorization still authenticates.
    # ------------------------------------------------------------------
    plaintext_key = "issue513-valid-key"
    key_digest = _sha256_hex(plaintext_key)

    with get_cursor() as cur:
        cur.execute(
            "UPDATE feed_credentials SET key_hash = %s, principal = %s, "
            "revoked = FALSE WHERE id = %s",
            (key_digest, "svc", entity_id),
        )

    # {X-Api-Key: valid, Authorization: Bearer x} -> 200
    combined = client.get(
        "/api/feed/v4",
        headers={"X-Api-Key": plaintext_key, "Authorization": "Bearer x"},
    )
    assert combined.status_code == 200, combined.text

    # A valid Basic Authorization header still authenticates.
    basic = client.get(
        "/api/feed/v4",
        headers={"Authorization": _basic("svc", plaintext_key)},
    )
    assert basic.status_code == 200, basic.text

    # ------------------------------------------------------------------
    # Criterion 3 — a malformed (non-ASCII) stored key_hash 401s instead of
    # 500ing, and other valid rows still authenticate.
    # ------------------------------------------------------------------
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO feed_credentials "
            "(id, name, principal, key_hash, key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, FALSE, NOW(), NOW())",
            ("issue513-malformed", "malformed", "svc", "h\u00e4sh", "abcd1234"),
        )

    # A request whose only matching row has the malformed hash 401s (not 500).
    malformed = client.get(
        "/api/feed/v4",
        headers={"Authorization": _basic("svc", "some-other-key")},
    )
    assert malformed.status_code == 401, malformed.text

    # The valid row still authenticates despite the malformed row existing.
    still_valid = client.get(
        "/api/feed/v4",
        headers={"Authorization": _basic("svc", plaintext_key)},
    )
    assert still_valid.status_code == 200, still_valid.text
