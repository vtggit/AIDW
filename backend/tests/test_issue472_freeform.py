"""Proof for issue #472 — $select and $orderby on the OData feed entity-set read.

Mounts the feed OData router on a fresh FastAPI app and exercises the
``$select`` / ``$orderby`` query options against a seeded dataset, using only
the existing database fixtures (no network, no hostnames, tenants or
credentials in code).
"""

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote

import psycopg2.extras
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.feed_odata import router as feed_odata_router
from app.db.connection import get_cursor

DATASET_NAME = "Feed Query Orders"
SET_NAME = "Feed_Query_Orders"
BASE_PATH = "/api/feed/v4"
PRINCIPAL = "feed-principal"
KEY = "feed-key-472"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed() -> None:
    """Seed a dataset, its fields, a feed credential and three payloads."""
    dataset_id = str(uuid.uuid4())
    field_ids = {
        "Order Id": str(uuid.uuid4()),
        "Order Date": str(uuid.uuid4()),
    }
    credential_id = str(uuid.uuid4())
    key_hash = hashlib.sha256(KEY.encode("utf-8")).hexdigest()
    key_prefix = KEY[:4]
    now = _now()
    payloads = [
        ("k1", {"Order Id": 1, "Order Date": "2024-01-20T00:00:00Z"}),
        ("k2", {"Order Id": 3, "Order Date": "2024-01-20T00:00:00Z"}),
        ("k3", {"Order Id": 2, "Order Date": "2024-01-10T00:00:00Z"}),
    ]
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s)",
            (dataset_id, DATASET_NAME, now, now),
        )
        for field_name, field_id in field_ids.items():
            data_type = (
                "Edm.Int32" if field_name == "Order Id" else "Edm.DateTimeOffset"
            )
            cur.execute(
                "INSERT INTO discovered_fields "
                "(id, name, data_type, dataset_id, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (field_id, field_name, data_type, dataset_id, now, now),
            )
        cur.execute(
            "INSERT INTO feed_credentials "
            "(id, name, principal, key_hash, key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                credential_id,
                "Feed Query Orders",
                PRINCIPAL,
                key_hash,
                key_prefix,
                False,
                now,
                now,
            ),
        )
        for business_key, payload in payloads:
            cur.execute(
                "INSERT INTO ingested_payloads "
                "(id, name, dataset_id, business_key, payload, ingested_at, "
                "created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    str(uuid.uuid4()),
                    f"payload-{business_key}",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(payload),
                    now,
                    now,
                    now,
                ),
            )


def _auth_headers() -> dict[str, str]:
    token = base64.b64encode(f"{PRINCIPAL}:{KEY}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _business_keys(body: dict) -> list[str]:
    return [row["business_key"] for row in body["value"]]


def _get(client: TestClient, query: str) -> TestClient:
    return client.get(f"{BASE_PATH}/{SET_NAME}{query}", headers=_auth_headers())


def test_issue472_freeform(clean_database):
    _seed()
    app = FastAPI()
    app.include_router(feed_odata_router)
    with TestClient(app) as client:
        # Baseline: no options — business keys in business_key order, full shape.
        resp = _get(client, "")
        assert resp.status_code == 200
        assert resp.headers["OData-Version"] == "4.0"
        body = resp.json()
        assert _business_keys(body) == ["k1", "k2", "k3"]
        for row in body["value"]:
            assert set(row.keys()) == {"business_key", "Order_Id", "Order_Date"}

        # $orderby=Order_Id (default asc).
        resp = _get(client, "?$orderby=Order_Id")
        assert resp.status_code == 200
        assert _business_keys(resp.json()) == ["k1", "k3", "k2"]

        # $orderby=Order_Id desc.
        resp = _get(client, "?$orderby=Order_Id desc")
        assert resp.status_code == 200
        assert _business_keys(resp.json()) == ["k2", "k3", "k1"]

        # $orderby=Order_Date asc,Order_Id desc — date tie decided by second key.
        resp = _get(client, "?$orderby=Order_Date asc,Order_Id desc")
        assert resp.status_code == 200
        assert _business_keys(resp.json()) == ["k3", "k2", "k1"]

        # $select=Order_Id — projected to exactly the selected property.
        resp = _get(client, "?$select=Order_Id")
        assert resp.status_code == 200
        body = resp.json()
        for row in body["value"]:
            assert set(row.keys()) == {"Order_Id"}
        assert [row["Order_Id"] for row in body["value"]] == [1, 3, 2]

        # $select=Order_Id,business_key — order preserved, no implicit key.
        resp = _get(client, "?$select=Order_Id,business_key")
        assert resp.status_code == 200
        for row in resp.json()["value"]:
            assert list(row) == ["Order_Id", "business_key"]

        # $select=Nope — 400 with OData error body and version header.
        resp = _get(client, "?$select=Nope")
        assert resp.status_code == 400
        assert resp.headers["OData-Version"] == "4.0"
        err = resp.json()["error"]
        assert err["code"] == "400"
        assert err["message"]

        # $orderby=Order_Id sideways — 400 with OData error body and header.
        resp = _get(client, "?$orderby=Order_Id sideways")
        assert resp.status_code == 400
        assert resp.headers["OData-Version"] == "4.0"
        err = resp.json()["error"]
        assert err["code"] == "400"
        assert err["message"]

        # $count=true&$orderby=Order_Id desc — count is the whole set.
        resp = _get(client, "?$count=true&$orderby=Order_Id desc")
        assert resp.status_code == 200
        assert resp.json()["@odata.count"] == 3

        # $top=1&$orderby=Order_Id desc — first page plus a nextLink that
        # preserves $skip, $top and $orderby.
        resp = _get(client, "?$top=1&$orderby=Order_Id desc")
        assert resp.status_code == 200
        body = resp.json()
        assert _business_keys(body) == ["k2"]
        next_link = unquote(body["@odata.nextLink"])
        assert "$skip=1" in next_link
        assert "$top=1" in next_link
        assert "$orderby=Order_Id desc" in next_link
