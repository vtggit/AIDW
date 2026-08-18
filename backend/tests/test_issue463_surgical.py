"""Proving test for issue #463: feed_odata router is mounted in create_app()."""

import app.api.feed_odata as feed_odata


def test_issue463_surgical(client):
    # 1. GET /api/feed/v4/ without credentials must return 401 with
    #    a WWW-Authenticate header starting with "Basic".
    resp = client.get("/api/feed/v4/")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    www_auth = resp.headers.get("WWW-Authenticate", "")
    assert www_auth.startswith(
        "Basic"
    ), f"WWW-Authenticate header should start with 'Basic', got: {www_auth!r}"

    # 2. Router identity check — the included router object must be
    #    feed_odata.router (FastAPI 0.141 wraps it in _IncludedRouter
    #    whose .original_router is the original router).
    app_instance = client.app
    found = any(
        getattr(r, "original_router", None) is feed_odata.router
        for r in app_instance.routes
    )
    assert found, "feed_odata.router not found among app.routes via original_router"

    # 3. Version-independent check: the path must appear in the OpenAPI
    #    schema.
    paths = app_instance.openapi()["paths"]
    assert (
        "/api/feed/v4/" in paths
    ), f"/api/feed/v4/ not in OpenAPI paths: {list(paths)}"
