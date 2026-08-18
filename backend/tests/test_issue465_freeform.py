"""Proof for issue #465 — OData v4 entity-set read on the feed surface.

Mounts the feed router on a fresh FastAPI app, seeds a dataset with two
discovered fields, a feed credential, and three ingested payloads, then
exercises the ``GET /{entity_set}`` route: credential gating, entity
rendering, paging ($top/$skip/$count), the FEED_PAGE_SIZE bound, the
unsupported-option 501, and the unknown-set 404.
"""

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

FEED_KEY = "feed-proof-key-0123456789abcdef"
PRINCIPAL = "feed-consumer"


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> str:
    """Insert the proof rows and return the dataset id."""
    dataset_id = uuid.uuid4().hex
    field_id_1 = uuid.uuid4().hex
    field_id_2 = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex
    payload_ids = [uuid.uuid4().hex for _ in range(3)]

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, "Feed Proof Orders"),
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
                "Feed Proof Credential",
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
                    "Feed Proof Payload",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(
                        {
                            "Order Id": order_id,
                            "Order Date": "2024-01-15T00:00:00Z",
                            "extra": "should-be-dropped",
                        }
                    ),
                ),
            )
    return dataset_id


def test_issue465_freeform(monkeypatch):
    _seed()

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)

    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}
    set_path = "/api/feed/v4/Feed_Proof_Orders"

    # --- 401 without feed credentials -------------------------------------
    response = client.get(set_path)
    assert response.status_code == 401

    # --- recorder over entity_set_names -----------------------------------
    original_entity_set_names = feed_odata.entity_set_names
    calls: list[list[dict]] = []

    def recording_entity_set_names(datasets):
        calls.append(list(datasets))
        return original_entity_set_names(datasets)

    monkeypatch.setattr(feed_odata, "entity_set_names", recording_entity_set_names)

    # --- 200 full read, headers, context, ordering, key set ---------------
    response = client.get(set_path, headers=auth)
    assert response.status_code == 200
    assert calls, "entity_set_names was not called"
    assert response.headers["OData-Version"] == "4.0"
    assert response.headers["content-type"].startswith(
        "application/json;odata.metadata=minimal"
    )
    body = response.json()
    assert body["@odata.context"].endswith("$metadata#Feed_Proof_Orders")
    value = body["value"]
    assert [row["business_key"] for row in value] == ["k1", "k2", "k3"]
    for row in value:
        assert set(row.keys()) == {"business_key", "Order_Id", "Order_Date"}
        assert "extra" not in row
    assert value[0]["Order_Id"] == 101
    assert value[1]["Order_Id"] == 102
    assert value[2]["Order_Id"] == 103
    assert value[0]["Order_Date"] == "2024-01-15T00:00:00Z"

    # --- $top=2 -> 2 rows + nextLink ($skip=2, $top=2) --------------------
    response = client.get(f"{set_path}?$top=2", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k1", "k2"]
    next_link = body["@odata.nextLink"]
    assert "$skip=2" in next_link
    assert "$top=2" in next_link

    # --- $skip=2 -> last row, no nextLink ---------------------------------
    response = client.get(f"{set_path}?$skip=2", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k3"]
    assert "@odata.nextLink" not in body

    # --- $count=true -> @odata.count = 3 ----------------------------------
    response = client.get(f"{set_path}?$count=true", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["@odata.count"] == 3
    assert len(body["value"]) == 3

    # --- FEED_PAGE_SIZE=2 bounds a read with no $top ----------------------
    monkeypatch.setenv("FEED_PAGE_SIZE", "2")
    response = client.get(set_path, headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k1", "k2"]
    assert "@odata.nextLink" in body
    monkeypatch.delenv("FEED_PAGE_SIZE")

    # --- unknown set -> 404 with OData error body -------------------------
    response = client.get("/api/feed/v4/Does_Not_Exist", headers=auth)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "404"
    assert "message" in error

    # --- unsupported system query option -> 501 ---------------------------
    response = client.get(f"{set_path}?$expand=Nope", headers=auth)
    assert response.status_code == 501
    error = response.json()["error"]
    assert error["code"] == "501"
    assert "message" in error
