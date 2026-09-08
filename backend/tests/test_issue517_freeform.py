"""Issue #517 — dual-form feed credential authentication.

Proves that when a request presents BOTH a parseable Basic credential and an
``X-Api-Key``:

* both forms resolving to the same non-revoked ``feed_credentials`` row
  authenticates as that row;
* the two forms resolving to different rows, or either one failing to resolve,
  is rejected with the same generic 401 + ``WWW-Authenticate`` challenge used
  for any other failure (no detail identifying which form failed, no fallback);
* presenting only one form (Basic alone, or ``X-Api-Key`` alone, including
  alongside a non-Basic ``Authorization`` header) keeps working exactly as
  before (PR#516's fix is preserved).

The tests drive the real ``/api/feed/v4`` surface through the ``client``
fixture against the real Postgres test database.
"""

import base64
import hashlib

from app.db.connection import get_cursor

# The feed service document route — every feed route depends on
# require_feed_credential, so it is the cleanest surface to probe auth.
_FEED_PATH = "/api/feed/v4/"

# The canonical 401 challenge the feed auth dependency always emits.
_WWW_AUTHENTICATE = 'Basic realm="AIDW feed"'


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _basic_header(principal: str, key: str) -> str:
    raw = f"{principal}:{key}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _seed_credential(
    entity_id: str,
    name: str,
    principal: str | None,
    key: str | None,
    revoked: bool | None = None,
) -> None:
    """Insert a feed_credentials row keyed by a known plaintext key.

    ``key_hash`` is the SHA-256 hex digest of ``key`` (or NULL when ``key`` is
    None).  ``revoked`` defaults to NULL (treated as not revoked by the auth
    dependency's ``revoked IS NOT TRUE`` filter).
    """
    key_hash = _sha256_hex(key) if key is not None else None
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO feed_credentials "
            "(id, name, principal, key_hash, key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (entity_id, name, principal, key_hash, (key or "")[:8], revoked),
        )


def _assert_generic_401(response) -> None:
    """Assert the response is the canonical generic 401 with the challenge."""
    assert response.status_code == 401, response.text
    assert response.headers.get("WWW-Authenticate") == _WWW_AUTHENTICATE
    body = response.json()
    # The generic detail — nothing that identifies which form failed.
    assert body.get("detail") == "Invalid or missing feed credential."


def test_issue517_freeform(client):
    # Two distinct, non-revoked credentials with different principals and keys.
    _seed_credential("fc-517-a", "cred-a", "principal-a", "key-a")
    _seed_credential("fc-517-b", "cred-b", "principal-b", "key-b")

    # ------------------------------------------------------------------
    # AC 1: both forms resolve to the SAME non-revoked row -> authenticates.
    # ------------------------------------------------------------------
    ok = client.get(
        _FEED_PATH,
        headers={
            "Authorization": _basic_header("principal-a", "key-a"),
            "X-Api-Key": "key-a",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.headers.get("OData-Version") == "4.0"

    # ------------------------------------------------------------------
    # AC 2a: both forms resolve to DIFFERENT rows -> generic 401, no fallback.
    # ------------------------------------------------------------------
    mismatch = client.get(
        _FEED_PATH,
        headers={
            "Authorization": _basic_header("principal-a", "key-a"),
            "X-Api-Key": "key-b",
        },
    )
    _assert_generic_401(mismatch)

    # ------------------------------------------------------------------
    # AC 2b: Basic form fails to resolve (wrong key) while X-Api-Key is valid
    # -> generic 401, no fallback to the valid form.
    # ------------------------------------------------------------------
    basic_bad = client.get(
        _FEED_PATH,
        headers={
            "Authorization": _basic_header("principal-a", "wrong-key"),
            "X-Api-Key": "key-b",
        },
    )
    _assert_generic_401(basic_bad)

    # ------------------------------------------------------------------
    # AC 2c: X-Api-Key form fails to resolve (unknown key) while Basic is valid
    # -> generic 401, no fallback to the valid form.
    # ------------------------------------------------------------------
    api_bad = client.get(
        _FEED_PATH,
        headers={
            "Authorization": _basic_header("principal-a", "key-a"),
            "X-Api-Key": "unknown-key",
        },
    )
    _assert_generic_401(api_bad)

    # ------------------------------------------------------------------
    # AC 2d: both forms present but the Basic row is REVOKED -> generic 401.
    # ------------------------------------------------------------------
    _seed_credential("fc-517-c", "cred-c", "principal-c", "key-c", revoked=True)
    revoked = client.get(
        _FEED_PATH,
        headers={
            "Authorization": _basic_header("principal-c", "key-c"),
            "X-Api-Key": "key-c",
        },
    )
    _assert_generic_401(revoked)

    # ------------------------------------------------------------------
    # AC 3: single-form presentation keeps working exactly as before.
    # ------------------------------------------------------------------
    # Basic alone.
    basic_alone = client.get(
        _FEED_PATH,
        headers={"Authorization": _basic_header("principal-b", "key-b")},
    )
    assert basic_alone.status_code == 200, basic_alone.text

    # X-Api-Key alone.
    api_alone = client.get(_FEED_PATH, headers={"X-Api-Key": "key-b"})
    assert api_alone.status_code == 200, api_alone.text

    # X-Api-Key alongside a NON-Basic Authorization header (PR#516's fix).
    api_with_bearer = client.get(
        _FEED_PATH,
        headers={"Authorization": "Bearer some-unrelated-token", "X-Api-Key": "key-b"},
    )
    assert api_with_bearer.status_code == 200, api_with_bearer.text

    # A non-Basic Authorization header with NO X-Api-Key still 401s (no form).
    bearer_only = client.get(
        _FEED_PATH, headers={"Authorization": "Bearer some-unrelated-token"}
    )
    _assert_generic_401(bearer_only)
