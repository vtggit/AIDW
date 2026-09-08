"""Proof for issue #545 — OData v4 feed treats ``$top`` as a total-row cap.

Mounts the feed router on a fresh FastAPI app, seeds a dataset with a page of
ingested payloads LARGER than the configured page size, and exercises the
``GET /{entity_set}`` route under the new ``$top`` semantics:

* ``$top=N`` caps the TOTAL rows a client receives across all pages, not the
  per-page size. The current page is limited to the remaining budget and
  ``@odata.nextLink`` is emitted only while the budget is not exhausted and
  more rows remain.
* Each emitted nextLink carries ``$top`` equal to the remaining budget (N minus
  the rows already delivered), not the original N.
* Following the emitted nextLinks yields exactly N rows in total, and the final
  page carries no ``@odata.nextLink``.
* A ``$top`` at or below the page size returns at most N rows with no nextLink.
* A ``$top`` greater than the total row count yields every row (no
  over-delivery, no under-delivery) and the final page carries no nextLink.
"""

import base64
import hashlib
import uuid

import psycopg2.extras
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.feed_odata import router as feed_odata_router
from app.db.connection import get_cursor

FEED_KEY = "feed-proof-key-0123456789abcdef"
PRINCIPAL = "feed-consumer"

# Dataset is larger than the page size; $top is greater than the page size.
_PAGE_SIZE = 2
_TOP = 5
_ROW_COUNT = 7


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> str:
    """Insert the proof rows and return the dataset id."""
    dataset_id = uuid.uuid4().hex
    field_id = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, "Feed Top Cap Orders"),
        )
        cur.execute(
            "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (field_id, "Order Id", "Edm.Int32", dataset_id),
        )
        cur.execute(
            "INSERT INTO feed_credentials (id, name, principal, key_hash, "
            "key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                credential_id,
                "Feed Top Cap Credential",
                PRINCIPAL,
                hashlib.sha256(FEED_KEY.encode("utf-8")).hexdigest(),
                FEED_KEY[:8],
                False,
            ),
        )
        for index in range(_ROW_COUNT):
            payload_id = uuid.uuid4().hex
            business_key = f"k{index:02d}"
            cur.execute(
                "INSERT INTO ingested_payloads (id, name, dataset_id, "
                "business_key, payload, ingested_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
                (
                    payload_id,
                    "Feed Top Cap Payload",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(
                        {
                            "Order Id": 100 + index,
                        }
                    ),
                ),
            )
    return dataset_id


def _follow(client: TestClient, auth: dict, body: dict) -> tuple[list[dict], dict]:
    """Follow emitted nextLinks until the budget is spent; return (rows, last body)."""
    collected: list[dict] = list(body["value"])
    while "@odata.nextLink" in body:
        next_link = body["@odata.nextLink"]
        # The nextLink is an absolute URL; extract its path + query and reissue
        # it against the test client.
        path_and_query = next_link.split("/api/feed/v4/", 1)[1]
        response = client.get(f"/api/feed/v4/{path_and_query}", headers=auth)
        assert response.status_code == 200
        body = response.json()
        collected.extend(body["value"])
    return collected, body


def test_issue545_freeform(monkeypatch):
    _seed()

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)

    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}
    set_path = "/api/feed/v4/Feed_Top_Cap_Orders"

    # The page size is read from the environment per request; pin it below $top
    # so a $top request spans multiple pages.
    monkeypatch.setenv("FEED_PAGE_SIZE", str(_PAGE_SIZE))

    # --- $top=N (N > page size): follow nextLinks, total == N -------------
    response = client.get(f"{set_path}?$top={_TOP}", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert response.headers["OData-Version"] == "4.0"
    assert body["@odata.context"].endswith("$metadata#Feed_Top_Cap_Orders")

    # First page holds min(page size, remaining budget) = page size rows.
    assert len(body["value"]) == _PAGE_SIZE
    # Budget not exhausted and more rows remain -> nextLink present, carrying
    # the REMAINING budget (N - rows delivered), not the original N.
    assert "@odata.nextLink" in body
    next_link = body["@odata.nextLink"]
    assert f"$skip={_PAGE_SIZE}" in next_link
    assert f"$top={_TOP - _PAGE_SIZE}" in next_link
    assert f"$top={_TOP}" not in next_link

    collected, body = _follow(client, auth, body)

    # The final page carries no nextLink (budget exhausted).
    assert "@odata.nextLink" not in body
    # Total rows received equals N exactly — not more.
    assert len(collected) == _TOP
    # Rows are the first N in business_key order, with no duplicates.
    assert [row["business_key"] for row in collected] == [
        f"k{i:02d}" for i in range(_TOP)
    ]

    # --- $top greater than the total row count: all rows, no over-delivery -
    response = client.get(f"{set_path}?$top={_ROW_COUNT + 3}", headers=auth)
    assert response.status_code == 200
    body = response.json()
    collected, body = _follow(client, auth, body)
    assert "@odata.nextLink" not in body
    assert len(collected) == _ROW_COUNT
    assert [row["business_key"] for row in collected] == [
        f"k{i:02d}" for i in range(_ROW_COUNT)
    ]

    # --- $top at or below the page size: at most N rows, no nextLink ------
    response = client.get(f"{set_path}?$top={_PAGE_SIZE}", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert len(body["value"]) == _PAGE_SIZE
    assert "@odata.nextLink" not in body

    response = client.get(f"{set_path}?$top=1", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert len(body["value"]) == 1
    assert body["value"][0]["business_key"] == "k00"
    assert "@odata.nextLink" not in body
