"""Proving test for issue #494: Cache-Control on metadata, absent on entity-set."""

from unittest.mock import patch


def test_issue494_surgical(client, app, monkeypatch):
    """Service doc and $metadata carry Cache-Control; entity-set does not."""
    from app.api.feed_odata import _metadata_max_age
    from app.feed.auth import require_feed_credential

    # Override feed credential dependency so routes are accessible.
    monkeypatch.setitem(
        app.dependency_overrides,
        require_feed_credential,
        lambda: {"id": "test"},
    )

    # --- Unit test _metadata_max_age read-at-call-time ---
    monkeypatch.setenv("FEED_METADATA_MAX_AGE", "120")
    assert _metadata_max_age() == 120

    monkeypatch.setenv("FEED_METADATA_MAX_AGE", "not_a_number")
    assert _metadata_max_age() == 300

    monkeypatch.delenv("FEED_METADATA_MAX_AGE", raising=False)
    assert _metadata_max_age() == 300

    # --- Service document: Cache-Control with custom max-age ---
    monkeypatch.setenv("FEED_METADATA_MAX_AGE", "120")
    resp = client.get("/api/feed/v4/")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=120"

    # --- $metadata: Cache-Control with custom max-age ---
    resp = client.get("/api/feed/v4/$metadata")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=120"

    # --- Read-at-call-time: change env, verify new value ---
    monkeypatch.setenv("FEED_METADATA_MAX_AGE", "60")
    resp = client.get("/api/feed/v4/")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=60"

    # --- Invalid value defaults to 300 ---
    monkeypatch.setenv("FEED_METADATA_MAX_AGE", "not_a_number")
    resp = client.get("/api/feed/v4/$metadata")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=300"

    # --- Unset defaults to 300 ---
    monkeypatch.delenv("FEED_METADATA_MAX_AGE", raising=False)
    resp = client.get("/api/feed/v4/")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=300"

    # --- Entity-set data response: NO Cache-Control header ---
    fake_datasets = [{"id": "ds1", "name": "TestDS", "created_at": None}]
    with (
        patch(
            "app.api.feed_odata.entity_set_names",
            return_value={"TestDS": "ds1"},
        ),
        patch(
            "app.api.feed_odata._load_datasets",
            return_value=fake_datasets,
        ),
        patch("app.api.feed_odata._load_fields", return_value=[]),
        patch("app.api.feed_odata._load_payloads", return_value=[]),
    ):
        resp = client.get("/api/feed/v4/TestDS")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers
