"""Proof for issue #474 — $filter on the OData v4 feed entity-set read.

Mounts the feed router on a fresh FastAPI app, seeds a dataset with two
discovered fields, a feed credential, and three ingested payloads, then
exercises ``GET /{entity_set}`` with ``$filter``: the filter is parsed once
per request and applied to each rendered entity before ``$orderby``,
``$skip``, ``$top`` and any ``$select`` projection; ``@odata.count`` and the
``@odata.nextLink`` reflect the filtered total; a bad property or a bad
expression returns 400; and the feed delegates to
``app.feed.filter_eval.evaluate`` over the rendered entity rather than
re-implementing the filter.
"""

import base64
import hashlib
import uuid

import psycopg2.extras
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.feed_odata as feed_odata
from app.api.feed_odata import router as feed_odata_router
from app.db.connection import get_cursor
from app.feed.naming import odata_identifier

FEED_KEY = "feed-filter-proof-key-0123456789abcdef"
PRINCIPAL = "feed-filter-consumer"


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> str:
    """Insert the proof rows and return the OData entity-set name."""
    dataset_id = uuid.uuid4().hex
    field_id_1 = uuid.uuid4().hex
    field_id_2 = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex
    payload_ids = [uuid.uuid4().hex for _ in range(3)]
    dataset_name = "Feed Filter Proof " + uuid.uuid4().hex[:8]

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, dataset_name),
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
                "Feed Filter Proof Credential",
                PRINCIPAL,
                hashlib.sha256(FEED_KEY.encode("utf-8")).hexdigest(),
                FEED_KEY[:8],
                False,
            ),
        )
        for payload_id, business_key, order_id, order_date in zip(
            payload_ids,
            ("k1", "k2", "k3"),
            (1, 2, 3),
            (
                "2024-01-01T00:00:00Z",
                "2024-01-02T00:00:00Z",
                "2024-01-03T00:00:00Z",
            ),
        ):
            cur.execute(
                "INSERT INTO ingested_payloads (id, name, dataset_id, "
                "business_key, payload, ingested_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
                (
                    payload_id,
                    "Feed Filter Proof Payload",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(
                        {
                            "Order Id": order_id,
                            "Order Date": order_date,
                        }
                    ),
                ),
            )
    return odata_identifier(dataset_name)


def test_issue474_freeform(monkeypatch):
    set_name = _seed()

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)

    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}
    set_path = f"/api/feed/v4/{set_name}"

    # --- $filter=Order_Id gt 1 with $count=true -> [k2, k3], count 2 ------
    response = client.get(
        set_path,
        headers=auth,
        params={"$filter": "Order_Id gt 1", "$count": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k2", "k3"]
    assert body["@odata.count"] == 2

    # --- $filter with a second clause -> exactly [k2] ---------------------
    response = client.get(
        set_path,
        headers=auth,
        params={
            "$filter": "Order_Id gt 1 and Order_Date lt '2024-01-02T12:00:00Z'",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k2"]

    # --- $filter on an unknown property -> 400 ----------------------------
    response = client.get(
        set_path,
        headers=auth,
        params={"$filter": "Nope eq 1"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "400"
    assert "message" in error
    assert response.headers["OData-Version"] == "4.0"

    # --- $filter with an unsupported function -> 400 ----------------------
    response = client.get(
        set_path,
        headers=auth,
        params={"$filter": "contains(Order_Id,1)"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "400"
    assert "message" in error
    assert response.headers["OData-Version"] == "4.0"

    # --- the feed delegates to app.feed.filter_eval.evaluate --------------
    original = feed_odata.evaluate
    recorded: list[tuple] = []

    def recorder(ast, row, types):
        recorded.append((ast, row, types))
        return original(ast, row, types)

    monkeypatch.setattr(feed_odata, "evaluate", recorder)

    response = client.get(
        set_path,
        headers=auth,
        params={"$filter": "Order_Id gt 1", "$top": "1", "$count": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k2"]
    assert body["@odata.count"] == 2
    next_link = body["@odata.nextLink"]
    assert "$filter" in next_link
    assert "$skip=1" in next_link

    assert len(recorded) >= 3
    expected_ast = ("cmp", "gt", "Order_Id", 1)
    expected_types = {
        "business_key": "Edm.String",
        "Order_Id": "Edm.Int32",
        "Order_Date": "Edm.DateTimeOffset",
    }
    for ast, row, types in recorded:
        assert ast == expected_ast
        assert types == expected_types
        assert isinstance(row, dict)
        assert set(row.keys()) == {"business_key", "Order_Id", "Order_Date"}

    # --- regression: no $filter with $count=true -> all three, count 3 ----
    response = client.get(
        set_path,
        headers=auth,
        params={"$count": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["business_key"] for row in body["value"]] == ["k1", "k2", "k3"]
    assert body["@odata.count"] == 3

    # --- regression: $expand stays unsupported -> 501 ---------------------
    response = client.get(
        set_path,
        headers=auth,
        params={"$expand": "x"},
    )
    assert response.status_code == 501
