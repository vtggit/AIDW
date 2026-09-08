"""Proof for issue #542 — external base URL in OData v4 feed responses."""

import base64
import hashlib
import uuid

import psycopg2.extras
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.feed_odata as feed_odata
from app.api.feed_odata import router as feed_odata_router
from app.db.connection import get_cursor

FEED_KEY = "feed-542-key-0123456789abcdef"
PRINCIPAL = "feed-542-consumer"
EXTERNAL_URL = "https://feed.example.com"


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> str:
    """Insert proof rows and return the dataset id."""
    dataset_id = uuid.uuid4().hex
    field_id_1 = uuid.uuid4().hex
    field_id_2 = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex
    payload_ids = [uuid.uuid4().hex for _ in range(3)]

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, "Feed 542 Orders"),
        )
        cur.execute(
            "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (field_id_1, "Order Id", "Edm.Int32", dataset_id),
        )
        cur.execute(
            "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (field_id_2, "Order Date", "Edm.DateTimeOffset", dataset_id),
        )
        cur.execute(
            "INSERT INTO feed_credentials (id, name, principal, key_hash, "
            "key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                credential_id,
                "Feed 542 Credential",
                PRINCIPAL,
                hashlib.sha256(FEED_KEY.encode("utf-8")).hexdigest(),
                FEED_KEY[:8],
                False,
            ),
        )
        for payload_id, business_key, order_id in zip(
            payload_ids, ("k1", "k2", "k3"), (101, 102, 103)
        ):
            cur.execute(
                "INSERT INTO ingested_payloads (id, name, dataset_id, "
                "business_key, payload, ingested_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
                (
                    payload_id,
                    "Feed 542 Payload",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(
                        {
                            "Order Id": order_id,
                            "Order Date": "2024-01-15T00:00:00Z",
                        }
                    ),
                ),
            )
    return dataset_id


def test_issue542_surgical(monkeypatch):
    _seed()

    monkeypatch.setattr(feed_odata, "FEED_EXTERNAL_BASE_URL", EXTERNAL_URL)

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)

    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}
    set_path = "/api/feed/v4/Feed_542_Orders"

    # --- $top=2 produces @odata.nextLink and @odata.context ---------------
    monkeypatch.setenv("FEED_PAGE_SIZE", "1")
    response = client.get(f"{set_path}?$top=2", headers=auth)
    assert response.status_code == 200
    body = response.json()

    # @odata.context must use the external base URL
    context = body["@odata.context"]
    assert context.startswith(f"{EXTERNAL_URL}/api/feed/v4/$metadata")
    assert "feed.example.com" in context

    # @odata.nextLink must use the external base URL
    next_link = body["@odata.nextLink"]
    assert next_link.startswith(f"{EXTERNAL_URL}/api/feed/v4/")
    assert "feed.example.com" in next_link
    assert "$skip=1" in next_link
    assert "$top=1" in next_link
    monkeypatch.delenv("FEED_PAGE_SIZE")

    # --- service document also uses external base URL ---------------------
    response = client.get("/api/feed/v4/", headers=auth)
    assert response.status_code == 200
    svc_body = response.json()
    assert svc_body["@odata.context"].startswith(
        f"{EXTERNAL_URL}/api/feed/v4/$metadata"
    )
