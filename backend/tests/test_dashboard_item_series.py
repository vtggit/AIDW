"""Computed-series proving test for dashboard_items (engine-generated,
computed-series lane): series math per enabled aggregation, the egress gate,
404, the RTBF suppression drop (post-suppression sample_size — no erasure
telegraph) and the fail-closed missing pepper."""

import json
import uuid

import pytest

_ROWS = [
    {"rid": 1, "region": "A", "val": 10},
    {"rid": 2, "region": "A", "val": 20},
    {"rid": 3, "region": "B", "val": 5},
]
_ROWS_JSON = json.dumps({"value": _ROWS}).encode()
_PEPPER = "engine-proof-pepper"


def _rid():
    return uuid.uuid4().hex


def test_dashboard_item_series_series(client, admin_headers, monkeypatch):
    from app.db.connection import get_cursor
    from app.governance.hashing import subject_key_hash
    from app.series.dashboard_item_series import series_data

    monkeypatch.setattr("app.config.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr(
        "app.series.dashboard_item_series._fetch_rows",
        lambda url: _ROWS_JSON,
    )
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", _PEPPER)

    # seed the resolution chain: source parent -> dataset -> connection ->
    # key/dimension/measure fields; items + role rows are seeded per aggregation
    src_id, ds_id = _rid(), _rid()
    f_key, f_dim, f_meas = _rid(), _rid(), _rid()
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO sources (id, name) VALUES (%s, %s)",
            (src_id, f"series-proof-{src_id[:8]}"),
        )
        cur.execute(
            "INSERT INTO datasets (id, name, source_id) VALUES (%s, %s, %s)",
            (ds_id, "Orders", src_id),
        )
        cur.execute(
            "INSERT INTO source_connections (id, name, endpoint, source_id) "
            "VALUES (%s, %s, %s, %s)",
            (_rid(), "conn", "https://svc.example/odata", src_id),
        )
        for fid, fname, is_key, pos in (
            (f_key, "rid", True, 1),
            (f_dim, "region", False, 2),
            (f_meas, "val", False, 3),
        ):
            cur.execute(
                "INSERT INTO discovered_fields (id, name, dataset_id, is_key, "
                "field_position) VALUES (%s, %s, %s, %s, %s)",
                (fid, fname, ds_id, is_key, pos),
            )

    def _make_item(item_id, agg):
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO dashboard_items (id, name, aggregation) "
                "VALUES (%s, %s, %s)",
                (item_id, f"item-{agg}", agg),
            )
            roles = [(f_dim, "dimension")]
            if agg in ("sum", "avg"):
                roles.append((f_meas, "measure"))
            for fid, role in roles:
                cur.execute(
                    "INSERT INTO dashboard_item_fields (id, name, dashboard_item_id, "
                    "discovered_field_id, field_role) VALUES (%s, %s, %s, %s, %s)",
                    (_rid(), f"{role}-role", item_id, fid, role),
                )

    _make_item(item_count := _rid(), "count")
    r = client.get(
        f"/api/dashboard-items/{item_count}/series",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["series"] == [
        {"label": "A", "value": 2},
        {"label": "B", "value": 1},
    ]
    _make_item(item_sum := _rid(), "sum")
    r = client.get(
        f"/api/dashboard-items/{item_sum}/series",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["series"] == [
        {"label": "A", "value": 30.0},
        {"label": "B", "value": 5.0},
    ]
    _make_item(item_avg := _rid(), "avg")
    r = client.get(
        f"/api/dashboard-items/{item_avg}/series",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["series"] == [
        {"label": "A", "value": 15.0},
        {"label": "B", "value": 5.0},
    ]
    # PII: an ACTIVE flag on a referenced field withholds the whole item (422);
    # a dismissed flag does not block. Seeding 'flagged' also makes any product
    # whose status vocabulary differs go loudly red here instead of silently
    # never matching the withhold predicate.
    flag_id = _rid()
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO pii_flags (id, name, dataset_id, discovered_field_id, "
            "status) VALUES (%s, %s, %s, %s, %s)",
            (flag_id, "flag", ds_id, f_dim, "flagged"),
        )
    r = client.get(
        f"/api/dashboard-items/{item_count}/series",
        headers=admin_headers,
    )
    assert r.status_code == 422
    with get_cursor() as cur:
        cur.execute(
            "UPDATE pii_flags SET status = %s WHERE id = %s",
            ("dismissed", flag_id),
        )
    r = client.get(
        f"/api/dashboard-items/{item_count}/series",
        headers=admin_headers,
    )
    assert r.status_code == 200

    # 404: unknown item
    r = client.get(
        "/api/dashboard-items/no-such-id/series",
        headers=admin_headers,
    )
    assert r.status_code == 404

    # RTBF: erase rid=1 (an A row) — the series and sample_size shrink and the
    # response never carries a pre-suppression count to diff against
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO suppression_entries (id, name, key_hash, dataset_id) "
            "VALUES (%s, %s, %s, %s)",
            (_rid(), "suppr", subject_key_hash(ds_id, "1"), ds_id),
        )
    r = client.get(
        f"/api/dashboard-items/{item_count}/series",
        headers=admin_headers,
    )
    assert r.json()["sample_size"] == 2
    assert "rows_used" not in r.json()

    # fail closed: entries exist but the pepper is missing
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER")
    with pytest.raises(RuntimeError):
        series_data(item_count)

    # egress off: 503, no fetch
    monkeypatch.setattr("app.config.ENABLE_INAPI_EGRESS", False)
    r = client.get(
        f"/api/dashboard-items/{item_count}/series",
        headers=admin_headers,
    )
    assert r.status_code == 503
