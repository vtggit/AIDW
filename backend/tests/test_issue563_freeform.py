"""Proof for issue #563 — OData v4 feed disambiguates colliding field identifiers.

Mounts the feed router on a fresh FastAPI app and seeds a dataset whose two
discovered fields sanitize to the same OData identifier (``Order-Id`` and
``Order Id`` both sanitize to ``Order_Id``). The proof runs through the HTTP
endpoints of the OData v4 feed (``/api/feed/v4``) and asserts:

* ``$metadata`` emits the disambiguated identifiers ``Order_Id`` and
  ``Order_Id2`` as CSDL ``Property`` names — the position-1 field keeps the
  base identifier, the position-2 field gets the numeric suffix, and no
  name is emitted twice.
* Every entity in the entity-set response carries that SAME pair of
  identifiers as keys (plus ``business_key``), so the CSDL and the payload
  agree and no field's data is shadowed.
* ``$filter`` ``eq`` on each identifier resolves to that identifier's own
  field: the literal ``30`` matches a different row under ``Order_Id`` than
  under ``Order_Id2``, and each ``eq`` returns only its matching row.
* ``$orderby`` asc and desc on the suffixed identifier ``Order_Id2`` order
  the rows by the position-2 field's values, not the position-1 field's.

Authentication to the feed follows ``test_issue561_freeform.py`` exactly: a
seeded feed credential and HTTP Basic with the principal and the plaintext
key.
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

SET_NAME = "Issue_563_Orders"
SET_PATH = f"/api/feed/v4/{SET_NAME}"

# (business_key, "Order-Id" value, "Order Id" value) per row. The two
# fields' values differ per row, and the value 30 sits under different
# fields for different rows, so each identifier's ``eq`` must resolve to
# its own field:
#
#   k001: Order_Id=10  Order_Id2=30   ("Order Id" is 30 here)
#   k002: Order_Id=20  Order_Id2=10
#   k003: Order_Id=30  Order_Id2=20   ("Order-Id" is 30 here)
ROWS = [
    ("k001", 10, 30),
    ("k002", 20, 10),
    ("k003", 30, 20),
]


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> None:
    """Insert the proof rows: one dataset, two colliding fields, three payloads.

    The two discovered fields, in canonical (``field_position`` then
    ``name``) order, both sanitize to the same OData identifier:

    1. ``Order-Id`` (position 1) -> ``Order_Id`` (keeps the base)
    2. ``Order Id`` (position 2) -> ``Order_Id`` (collision -> ``Order_Id2``)
    """
    dataset_id = uuid.uuid4().hex
    field_id_a = uuid.uuid4().hex
    field_id_b = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, "Issue 563 Orders"),
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
            "INSERT INTO feed_credentials (id, name, principal, key_hash, "
            "key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                credential_id,
                "Issue 563 Feed Credential",
                PRINCIPAL,
                hashlib.sha256(FEED_KEY.encode("utf-8")).hexdigest(),
                FEED_KEY[:8],
                False,
            ),
        )
        for business_key, base_value, suffixed_value in ROWS:
            payload_id = uuid.uuid4().hex
            cur.execute(
                "INSERT INTO ingested_payloads (id, name, dataset_id, "
                "business_key, payload, ingested_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
                (
                    payload_id,
                    "Issue 563 Payload",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(
                        {"Order-Id": base_value, "Order Id": suffixed_value}
                    ),
                ),
            )


def _property_names(xml: str) -> list[str]:
    """Return the ``Name`` attributes of every ``<Property>`` element, in order."""
    return re.findall(r'<Property Name="([^"]+)"', xml)


def _keys(response) -> list[str]:
    """Return the ``business_key`` of each entity in the response, in order."""
    return [entity["business_key"] for entity in response.json()["value"]]


def test_issue563_freeform():
    _seed()

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)

    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}

    # --- $metadata: CSDL Property names are the disambiguated identifiers --
    response = client.get("/api/feed/v4/$metadata", headers=auth)
    assert response.status_code == 200
    assert response.headers["OData-Version"] == "4.0"
    names = _property_names(response.text)
    # business_key is the key property, then the two fields in canonical
    # order: the position-1 field ("Order-Id") keeps the base, the
    # position-2 field ("Order Id") is suffixed.
    assert names == ["business_key", "Order_Id", "Order_Id2"]
    # No identifier is emitted twice (CSDL stays schema-valid).
    assert len(names) == len(set(names))
    csdl_identifiers = set(names) - {"business_key"}
    assert csdl_identifiers == {"Order_Id", "Order_Id2"}

    # --- entity-set response: the same identifiers key every entity --------
    response = client.get(SET_PATH, headers=auth)
    assert response.status_code == 200
    assert response.headers["OData-Version"] == "4.0"
    body = response.json()
    assert body["@odata.context"].endswith(f"#{SET_NAME}")
    assert len(body["value"]) == len(ROWS)

    entities = {entity["business_key"]: entity for entity in body["value"]}
    for business_key, base_value, suffixed_value in ROWS:
        entity = entities[business_key]
        # Each entity's keys are exactly the CSDL property names: the same
        # disambiguated identifiers, nothing shadowed, nothing extra.
        assert set(entity) == {"business_key"} | csdl_identifiers
        # Each identifier is valued by its own field.
        assert entity["Order_Id"] == base_value
        assert entity["Order_Id2"] == suffixed_value

    # --- $filter: eq on each identifier resolves to its own field ----------
    # The same literal (30) matches different rows under the two identifiers:
    # under the base it is k003's "Order-Id", under the suffix it is k001's
    # "Order Id". Each eq returns only its matching row.
    response = client.get(SET_PATH, headers=auth, params={"$filter": "Order_Id eq 30"})
    assert response.status_code == 200
    assert _keys(response) == ["k003"]
    assert response.json()["value"][0]["Order_Id"] == 30
    assert response.json()["value"][0]["Order_Id2"] == 20

    response = client.get(SET_PATH, headers=auth, params={"$filter": "Order_Id2 eq 30"})
    assert response.status_code == 200
    assert _keys(response) == ["k001"]
    assert response.json()["value"][0]["Order_Id"] == 10
    assert response.json()["value"][0]["Order_Id2"] == 30

    # A non-matching eq returns no rows at all.
    response = client.get(
        SET_PATH, headers=auth, params={"$filter": "Order_Id2 eq 999"}
    )
    assert response.status_code == 200
    assert response.json()["value"] == []

    # --- $orderby: asc and desc on the suffixed identifier ------------------
    # "Order Id" (Order_Id2) values: k002=10, k003=20, k001=30 — NOT the base
    # field's order (k001, k002, k003), proving the sort reads Order_Id2.
    response = client.get(SET_PATH, headers=auth, params={"$orderby": "Order_Id2 asc"})
    assert response.status_code == 200
    assert _keys(response) == ["k002", "k003", "k001"]

    response = client.get(SET_PATH, headers=auth, params={"$orderby": "Order_Id2 desc"})
    assert response.status_code == 200
    assert _keys(response) == ["k001", "k003", "k002"]
