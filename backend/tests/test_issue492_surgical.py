"""Proving test for issue #492: $top server maximum enforcement."""

import json
from unittest.mock import patch

from starlette.requests import Request

import app.api.feed_odata as feed_odata


def test_issue492_surgical(monkeypatch):
    """$top exceeding FEED_TOP_MAX is rejected with a typed OData 400."""
    monkeypatch.setenv("FEED_TOP_MAX", "10")

    with (
        patch.object(
            feed_odata,
            "_load_datasets",
            return_value=[
                {"id": "ds1", "name": "TestSet", "created_at": None},
            ],
        ),
        patch.object(
            feed_odata,
            "entity_set_names",
            return_value={"TestSet": "ds1"},
        ),
        patch.object(feed_odata, "_load_fields", return_value=[]),
        patch.object(feed_odata, "_load_payloads", return_value=[]),
    ):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/feed/v4/TestSet",
            "query_string": b"$top=100",
            "headers": [],
        }
        request = Request(scope)
        response = feed_odata.read_entity_set(
            "TestSet",
            request,
            _credential={},
        )

    assert response.status_code == 400
    data = json.loads(response.body)
    assert "error" in data
    assert "10" in data["error"]["message"]
