"""Proving test for Issue #406 — GET /api/load-sequences/due."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def _seed_load_sequences(client, admin_headers):
    """Create load sequences with various schedule states for testing.

    Returns a dict mapping sequence names to their created records, plus
    the reference timestamp used so the test can query consistently.
    """
    # Use a fixed reference point so timing between fixture setup and
    # the actual query is deterministic.
    ref_time = datetime.now(timezone.utc)

    seqs = {}

    # Sequence 1: enabled, has cadence, never fired (last_fired_at is NULL) -> DUE
    r1 = client.post(
        "/api/load-sequences",
        headers=admin_headers,
        json={
            "name": "seq-always-due",
            "schedule_cadence": "daily",
            "schedule_enabled": True,
        },
    )
    assert r1.status_code == 201, r1.text
    seqs["seq-always-due"] = r1.json()

    # Sequence 2: enabled, has cadence, fired long ago -> DUE
    r2 = client.post(
        "/api/load-sequences",
        headers=admin_headers,
        json={
            "name": "seq-fired-long-ago",
            "schedule_cadence": "weekly",
            "schedule_enabled": True,
        },
    )
    assert r2.status_code == 201, r2.text
    seq_id_2 = r2.json()["id"]
    old_time = (ref_time - timedelta(days=30)).isoformat()
    upd2 = client.put(
        f"/api/load-sequences/{seq_id_2}",
        headers=admin_headers,
        json={"last_fired_at": old_time},
    )
    assert upd2.status_code == 200, upd2.text
    seqs["seq-fired-long-ago"] = upd2.json()

    # Sequence 3: enabled, has cadence, fired recently (AFTER ref_time) -> NOT DUE
    # because last_fired_at > not_fired_since means it was fired after the threshold.
    r3 = client.post(
        "/api/load-sequences",
        headers=admin_headers,
        json={
            "name": "seq-fired-recently",
            "schedule_cadence": "hourly",
            "schedule_enabled": True,
        },
    )
    assert r3.status_code == 201, r3.text
    seq_id_3 = r3.json()["id"]
    recent_time = (ref_time + timedelta(minutes=5)).isoformat()
    upd3 = client.put(
        f"/api/load-sequences/{seq_id_3}",
        headers=admin_headers,
        json={"last_fired_at": recent_time},
    )
    assert upd3.status_code == 200, upd3.text
    seqs["seq-fired-recently"] = upd3.json()

    # Sequence 4: disabled (schedule_enabled=False) -> NOT DUE regardless of cadence/fired
    r4 = client.post(
        "/api/load-sequences",
        headers=admin_headers,
        json={
            "name": "seq-disabled",
            "schedule_cadence": "daily",
            "schedule_enabled": False,
        },
    )
    assert r4.status_code == 201, r4.text
    seqs["seq-disabled"] = r4.json()

    # Sequence 5: no cadence -> NOT DUE regardless of enabled/fired
    r5 = client.post(
        "/api/load-sequences",
        headers=admin_headers,
        json={
            "name": "seq-no-cadence",
            "schedule_enabled": True,
        },
    )
    assert r5.status_code == 201, r5.text
    seqs["seq-no-cadence"] = r5.json()

    return {"sequences": seqs, "ref_time": ref_time}


def test_issue406_freeform(client, admin_headers, _seed_load_sequences):
    """Verify GET /api/load-sequences/due returns only due sequences."""
    seqs = _seed_load_sequences["sequences"]
    ref_time = _seed_load_sequences["ref_time"]

    # Use the same reference time that was used to set last_fired_at values.
    now_iso = ref_time.isoformat()

    resp = client.get(
        "/api/load-sequences/due",
        headers=admin_headers,
        params={"not_fired_since": now_iso},
    )
    assert resp.status_code == 200, resp.text

    due_list = resp.json()
    due_names = {item["name"] for item in due_list}

    # seq-always-due: NULL last_fired_at -> DUE
    assert (
        "seq-always-due" in due_names
    ), f"Expected 'seq-always-due' to be due. Got: {due_names}"

    # seq-fired-long-ago: fired 30 days before ref_time -> DUE
    assert (
        "seq-fired-long-ago" in due_names
    ), f"Expected 'seq-fired-long-ago' to be due. Got: {due_names}"

    # seq-fired-recently: last_fired_at is AFTER ref_time -> NOT DUE
    assert (
        "seq-fired-recently" not in due_names
    ), f"'seq-fired-recently' should NOT be due when threshold is now. Got: {due_names}"

    # seq-disabled: schedule_enabled=False -> NOT DUE
    assert (
        "seq-disabled" not in due_names
    ), f"'seq-disabled' should NOT be due. Got: {due_names}"

    # seq-no-cadence: no schedule_cadence -> NOT DUE
    assert (
        "seq-no-cadence" not in due_names
    ), f"'seq-no-cadence' should NOT be due. Got: {due_names}"

    # Verify each entry carries the required fields
    for item in due_list:
        assert "id" in item
        assert "name" in item
        assert "schedule_cadence" in item
        assert "schedule_enabled" in item
        assert "last_fired_at" in item

    # Verify that existing routes still work (list, get)
    list_resp = client.get("/api/load-sequences", headers=admin_headers)
    assert list_resp.status_code == 200

    first_seq_id = seqs["seq-always-due"]["id"]
    get_resp = client.get(f"/api/load-sequences/{first_seq_id}", headers=admin_headers)
    assert get_resp.status_code == 200
