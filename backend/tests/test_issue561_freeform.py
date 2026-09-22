"""Proof for issue #561 — OData v4 feed disambiguates colliding field identifiers.

Mounts the feed router on a fresh FastAPI app, seeds a dataset whose discovered
fields sanitize to the same OData identifier, and asserts:

* ``$metadata`` emits distinct identifiers in ``field_position``-then-``name``
  order — the first field in that order keeps the base identifier, the second
  gets the numeric suffix, and a third field whose base matches a generated
  suffix is pushed to the next free identifier (no duplicate ``<Property>``).
* The entity payload carries every field's value under its distinct
  identifier, so no field's data is silently shadowed.

The seed is chosen so that the field whose NAME sorts first is NOT first in
canonical order, proving the ordering is by ``field_position`` then ``name``
(not by name alone): the base identifier is assigned to the position-1 field,
and the payload values land under the identifiers that ordering dictates.

Authentication to the feed follows ``test_issue545_freeform.py`` exactly: a
seeded feed credential and HTTP Basic with the principal and the plaintext key.
"""

import base64
import hashlib
import re
import uuid

import psycopg2.extras
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.feed_odata import router as feed_odata_router
from app.db.connection import get_cursor

FEED_KEY = "feed-proof-key-0123456789abcdef"
PRINCIPAL = "feed-consumer"


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> str:
    """Insert the proof rows and return the dataset id.

    Three discovered fields, in canonical (``field_position`` then ``name``)
    order:

    1. ``Order-Id``   (position 1) -> base ``Order_Id``
    2. ``Order Id``   (position 2) -> base ``Order_Id`` (collision -> ``Order_Id2``)
    3. ``Order_Id2``  (position 3) -> base ``Order_Id2`` (matches the suffix
       generated for field 2 -> pushed to ``Order_Id22``)

    By name, ``Order Id`` (space) sorts before ``Order-Id`` (hyphen), so the
    position-1 field is NOT the name-first field: this proves the ordering is
    by ``field_position`` then ``name``, not by name alone.
    """
    dataset_id = uuid.uuid4().hex
    field_id_a = uuid.uuid4().hex
    field_id_b = uuid.uuid4().hex
    field_id_c = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, "Feed Collision Orders"),
        )
        cur.execute(
            "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
            "field_position, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
            (field_id_a, "Order-Id", "Edm.Int32", dataset_id, 1),
        )
        cur.execute(
            "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
            "field_position, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
            (field_id_b, "Order Id", "Edm.Int32", dataset_id, 2),
        )
        cur.execute(
            "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
            "field_position, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
            (field_id_c, "Order_Id2", "Edm.Int32", dataset_id, 3),
        )
        cur.execute(
            "INSERT INTO feed_credentials (id, name, principal, key_hash, "
            "key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                credential_id,
                "Feed Collision Credential",
                PRINCIPAL,
                hashlib.sha256(FEED_KEY.encode("utf-8")).hexdigest(),
                FEED_KEY[:8],
                False,
            ),
        )
        payload_id = uuid.uuid4().hex
        cur.execute(
            "INSERT INTO ingested_payloads (id, name, dataset_id, "
            "business_key, payload, ingested_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
            (
                payload_id,
                "Feed Collision Payload",
                dataset_id,
                "k00",
                psycopg2.extras.Json(
                    {
                        "Order-Id": 222,
                        "Order Id": 111,
                        "Order_Id2": 333,
                    }
                ),
            ),
        )
    return dataset_id


def _property_names(xml: str) -> list[str]:
    """Return the ``Name`` attributes of every ``<Property>`` element, in order."""
    return re.findall(r'<Property Name="([^"]+)"', xml)


def test_issue561_freeform():
    _seed()

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)

    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}

    # --- $metadata: distinct identifiers in field_position-then-name order --
    response = client.get("/api/feed/v4/$metadata", headers=auth)
    assert response.status_code == 200
    assert response.headers["OData-Version"] == "4.0"
    xml = response.text

    names = _property_names(xml)
    # business_key is the key property, then the three disambiguated fields in
    # canonical order: the position-1 field keeps the base, the position-2
    # field is suffixed, and the position-3 field (whose base matches the
    # generated suffix) is pushed to the next free identifier.
    assert names == ["business_key", "Order_Id", "Order_Id2", "Order_Id22"]
    # No identifier is emitted twice (CSDL stays schema-valid).
    assert len(names) == len(set(names))

    # --- entity payload: every field's value under its distinct identifier --
    set_path = "/api/feed/v4/Feed_Collision_Orders"
    response = client.get(set_path, headers=auth)
    assert response.status_code == 200
    assert response.headers["OData-Version"] == "4.0"
    body = response.json()
    assert body["@odata.context"].endswith("#Feed_Collision_Orders")

    assert len(body["value"]) == 1
    entity = body["value"][0]
    assert entity["business_key"] == "k00"
    # The position-1 field ("Order-Id") keeps the base identifier; the
    # position-2 field ("Order Id") is suffixed; the position-3 field
    # ("Order_Id2") is pushed to the next free identifier. No value is shadowed.
    assert entity["Order_Id"] == 222
    assert entity["Order_Id2"] == 111
    assert entity["Order_Id22"] == 333
