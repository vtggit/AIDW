"""Proof for issue #461 — OData v4 feed surface.

Mounts the feed router on a fresh app, seeds a dataset with two discovered
fields and a feed credential, then exercises the service document and the
CSDL 4.0 metadata document end to end.
"""

import base64
import hashlib
import uuid

from fastapi.testclient import TestClient

from app.db.connection import get_cursor
from app.feed.naming import odata_identifier


def test_issue461_freeform(app, monkeypatch):
    import app.api.feed_odata as feed_odata

    # --- Mount the feed router on the fresh app. ---
    app.include_router(feed_odata.router)

    # --- Seed a dataset, two discovered fields, and a feed credential. ---
    dataset_id = str(uuid.uuid4())
    dataset_name = "Feed Proof " + uuid.uuid4().hex[:8]
    field_a_id = str(uuid.uuid4())
    field_b_id = str(uuid.uuid4())
    field_a_name = "quantity"
    field_b_name = "occurred_at"
    cred_id = str(uuid.uuid4())
    principal = "principal-" + uuid.uuid4().hex
    key = uuid.uuid4().hex
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    key_prefix = key[:8]

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, dataset_name),
        )
        cur.execute(
            "INSERT INTO discovered_fields "
            "(id, name, data_type, dataset_id, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (field_a_id, field_a_name, "integer", dataset_id),
        )
        cur.execute(
            "INSERT INTO discovered_fields "
            "(id, name, data_type, dataset_id, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (field_b_id, field_b_name, "Edm.DateTime", dataset_id),
        )
        cur.execute(
            "INSERT INTO feed_credentials "
            "(id, name, principal, key_hash, key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (cred_id, "feed-proof", principal, key_hash, key_prefix, False),
        )

    set_name = odata_identifier(dataset_name)
    basic = "Basic " + base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    basic_headers = {"Authorization": basic}

    with TestClient(app) as client:
        # --- Unauthenticated service root is rejected. ---
        resp = client.get("/api/feed/v4/")
        assert resp.status_code == 401

        # --- With the credential dependency overridden, the service root answers. ---
        app.dependency_overrides[feed_odata.require_feed_credential] = lambda: {}
        try:
            resp = client.get("/api/feed/v4/")
            assert resp.status_code == 200
            assert resp.headers.get("OData-Version") == "4.0"
        finally:
            app.dependency_overrides.pop(feed_odata.require_feed_credential, None)

        # --- Record that the naming helper is actually invoked by the router. ---
        original_entity_set_names = feed_odata.entity_set_names
        calls = []

        def wrapper(datasets):
            calls.append(datasets)
            return original_entity_set_names(datasets)

        monkeypatch.setattr(feed_odata, "entity_set_names", wrapper)

        # --- Service document with real Basic auth. ---
        resp = client.get("/api/feed/v4/", headers=basic_headers)
        assert resp.status_code == 200
        assert resp.headers.get("OData-Version") == "4.0"
        body = resp.json()
        assert body["@odata.context"].endswith("/api/feed/v4/$metadata")
        assert {"name": set_name, "kind": "EntitySet", "url": set_name} in body["value"]
        assert calls, "entity_set_names was not called by the service document route"

        # --- CSDL 4.0 metadata document with real Basic auth. ---
        resp = client.get("/api/feed/v4/$metadata", headers=basic_headers)
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/xml")
        assert resp.headers.get("OData-Version") == "4.0"
        xml = resp.text

        assert f'<EntityType Name="{set_name}">' in xml
        assert '<PropertyRef Name="business_key"/>' in xml
        assert 'Name="business_key" Type="Edm.String" Nullable="false"' in xml
        assert (
            f'Name="{odata_identifier(field_a_name)}" Type="Edm.Int32" Nullable="true"'
            in xml
        )
        assert (
            f'Name="{odata_identifier(field_b_name)}" Type="Edm.DateTimeOffset" Nullable="true"'
            in xml
        )
        assert f'<EntitySet Name="{set_name}" EntityType="AIDW.{set_name}"/>' in xml
        assert '<EntityContainer Name="Container">' in xml
