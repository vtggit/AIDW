"""Cursor-ingest tests: the pure mapper/filter/cursor helpers, and the run endpoint (mocked data
egress, real Postgres) proving observable output state — op-log rows actually landed, the cursor
actually advanced, the run row actually carries the counts, and the §6 profile + re-score pass
actually fired on success.
"""

import json
import urllib.parse

import pytest

from app.ingest.cursor import _acceptable, _advance, _later
from app.ingest.filters import build_page_url
from app.ingest.mapper import (
    business_key,
    extract_entries,
    normalize_cursor_value,
    parse_rows,
)

# --------------------------------------------------------------------------- pure helpers


def test_parse_rows_v4_and_v2():
    v4 = json.dumps({"value": [{"a": 1}, {"a": 2}, "junk"]}).encode()
    v2 = json.dumps({"d": {"results": [{"b": 3}]}}).encode()
    assert parse_rows(v4) == [{"a": 1}, {"a": 2}]
    assert parse_rows(v2) == [{"b": 3}]
    assert parse_rows(b"{}") == []
    # the page-cap judgment counts entries AS FETCHED — junk still occupied a $top slot
    assert len(extract_entries(v4)) == 3


def test_business_key_composite_and_missing():
    assert business_key({"A": 1, "B": "x"}, ["A", "B"]) == "1|x"
    assert business_key({"A": 1}, ["A", "B"]) is None
    assert business_key({"A": None}, ["A"]) is None


def test_normalize_cursor_value_v2_date_and_iso():
    assert normalize_cursor_value("/Date(857439600000)/") == "857439600000"
    assert normalize_cursor_value("/Date(857439600000+0100)/") == "857439600000"
    assert normalize_cursor_value("1998-05-01T00:00:00Z") == "1998-05-01T00:00:00Z"
    assert normalize_cursor_value(None) is None
    assert normalize_cursor_value(42) == "42"
    # an absurd remote ms count stays an opaque string
    poison = "/Date(99999999999999999999)/"
    assert normalize_cursor_value(poison) == poison


def test_acceptable_gates_watermark_candidacy():
    """Only values that are orderable AND renderable as a $filter literal may become the
    watermark — otherwise one bad remote row wedges every future run of the pipeline."""
    # timestamp kind: in-range ms and real ISO-8601 pass; junk and out-of-range ms are rejected
    assert _acceptable("857439600000", "timestamp") is True
    assert _acceptable("1998-05-01T00:00:00Z", "timestamp") is True
    assert _acceptable("1998-05-01T00:00:00.123Z", "timestamp") is True
    assert _acceptable("1998-05-01", "timestamp") is True  # Edm.Date
    assert _acceptable("/Date(99999999999999999999)/", "timestamp") is False
    assert (
        _acceptable("300000000000000", "timestamp") is False
    )  # ~year 11476, unrenderable
    assert _acceptable("-99999999999999", "timestamp") is False  # far before year 1
    assert _acceptable("garbage", "timestamp") is False
    # digit-LEADING junk must not sneak past an ISO check (it would outrank ISO values as text)
    assert _acceptable("3-bad-data", "timestamp") is False
    assert _acceptable("31/12/2026", "timestamp") is False
    # numeric kind: must parse AND be finite (json.loads admits bare Infinity/NaN)
    assert _acceptable("42.5", "numeric") is True
    assert _acceptable("42 or true", "numeric") is False
    assert _acceptable("inf", "numeric") is False
    assert _acceptable("-inf", "numeric") is False
    assert _acceptable("nan", "numeric") is False
    assert _acceptable("1e999", "numeric") is False  # overflows to inf
    # string kind: anything goes (rendered quoted+escaped)
    assert _acceptable("O'Brien", "string") is True


def test_advance_is_page_cap_aware():
    """A full page may cut a tie group at its max value — the watermark must not advance past
    the cut (the strictly-greater filter would lose the rest of the tie forever)."""
    kind = "timestamp"
    d1, d2 = "1998-05-01T00:00:00Z", "1998-05-02T00:00:00Z"
    # page not full: plain max
    assert _advance([d1, d2], None, kind, page_full=False) == d2
    # full page, tie at the max: advance only to the greatest value below the max
    assert _advance([d1, d2, d2], None, kind, page_full=True) == d1
    # full page entirely tied: cannot advance
    assert _advance([d2, d2, d2], d1, kind, page_full=True) == d1
    assert _advance([d2, d2, d2], None, kind, page_full=True) is None
    # never regress an already-later watermark
    assert _advance([d1], d2, kind, page_full=False) == d2
    assert _advance([], d2, kind, page_full=True) == d2


def test_build_page_url_shapes():
    base = "https://svc.example/odata"
    # no cursor: plain page
    assert (
        build_page_url(base, "Orders", 500)
        == "https://svc.example/odata/Orders?$top=500&$format=json"
    )
    # cursor, no watermark yet: ordered, unfiltered
    url = build_page_url(base, "Orders", 500, "V4", "OrderDate", None, "timestamp")
    assert "$orderby=" in url and "$filter" not in url
    # V4 timestamp watermark: bare ISO literal
    url = build_page_url(
        base, "Orders", 500, "V4", "OrderDate", "1998-05-10T00:00:00Z", "timestamp"
    )
    assert "OrderDate gt 1998-05-10T00:00:00Z" in urllib.parse.unquote(url)
    # V2 timestamp watermark: datetime'' literal
    url = build_page_url(
        base, "Orders", 500, "V2", "OrderDate", "1998-05-10T00:00:00Z", "timestamp"
    )
    assert "OrderDate gt datetime'1998-05-10T00:00:00'" in urllib.parse.unquote(url)
    # normalized V2 /Date(ms)/ watermark folds back into a datetime'' literal
    url = build_page_url(
        base, "Orders", 500, "V2", "OrderDate", "894067200000", "timestamp"
    )
    assert "OrderDate gt datetime'1998-05-02T00:00:00'" in urllib.parse.unquote(url)
    # numeric watermark: bare, validated
    url = build_page_url(base, "Orders", 500, "V4", "OrderID", "42", "numeric")
    assert "OrderID gt 42" in urllib.parse.unquote(url)
    with pytest.raises(ValueError):
        build_page_url(base, "Orders", 500, "V4", "OrderID", "42 or true", "numeric")
    with pytest.raises(ValueError):  # non-finite must fail loud, never render 'gt inf'
        build_page_url(base, "Orders", 500, "V4", "OrderID", "inf", "numeric")
    # string watermark: quoted, embedded quotes doubled (the OData escape)
    url = build_page_url(base, "Orders", 500, "V4", "Name", "O'Brien", "string")
    assert "Name gt 'O''Brien'" in urllib.parse.unquote(url)


def test_later_is_kind_aware():
    assert _later("10", "9", "numeric") is True  # numeric, not lexicographic
    assert _later("10", "9", "string") is False  # lexicographic for strings
    assert _later("1998-05-02T00:00:00Z", "1998-05-01T00:00:00Z", "timestamp") is True
    assert _later("anything", None, "timestamp") is True
    assert _later("1998-05-01T00:00:00Z", "1998-05-01T00:00:00Z", "timestamp") is False


# --------------------------------------------------------------------------- endpoint (integration)

_RICH_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NW" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Order">
        <Key><PropertyRef Name="OrderID"/></Key>
        <Property Name="OrderID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="OrderDate" Type="Edm.DateTimeOffset"/>
        <Property Name="Freight" Type="Edm.Decimal"/>
        <Property Name="ShipCountry" Type="Edm.String"/>
        <Property Name="CustomerID" Type="Edm.Int32"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Orders" EntityType="NW.Order"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


def _rows_page(order_ids, month="05"):
    return json.dumps(
        {
            "value": [
                {
                    "OrderID": oid,
                    "OrderDate": f"1998-{month}-{(i % 27) + 1:02d}T00:00:00Z",
                    "Freight": 10.0 + i,
                    "ShipCountry": ["USA", "UK", "France"][i % 3],
                    "CustomerID": 100 + i,
                }
                for i, oid in enumerate(order_ids)
            ]
        }
    ).encode()


_PAGE_1 = _rows_page(range(10))  # OrderDate 1998-05-01 .. 1998-05-10
_PAGE_2 = _rows_page([100, 101], month="06")  # 1998-06-01, 1998-06-02


def _make_odata_source(client, admin_headers, endpoint="https://svc.example/odata"):
    sid = client.post(
        "/api/sources", json={"name": "nw", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={
            "name": "conn",
            "endpoint": endpoint,
            "protocol_version": "V4",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/odata-service-configs",
        json={
            "name": "cfg",
            "metadata_path": "$metadata",
            "default_entity_set": "Orders",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    return sid


def _discovered(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _RICH_EDMX)
    sid = _make_odata_source(client, admin_headers)
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    return sid


def _make_pipeline(client, admin_headers, sid):
    did = next(
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    )
    pid = client.post(
        "/api/pipelines",
        json={"name": "orders-pipe", "dataset_id": did, "cdc_pattern": "cursor"},
        headers=admin_headers,
    ).json()["id"]
    return pid, did


def _arm(client, admin_headers, monkeypatch, pages):
    """Enable egress, queue ingest fetch payloads (recording URLs), quiet the profiler egress."""
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    calls = []
    queue = list(pages)

    def fake_fetch(url):
        calls.append(url)
        return queue.pop(0)

    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _PAGE_1)
    return calls


def test_run_requires_admin(client, user_headers):
    assert client.post("/api/pipelines/x/runs", headers=user_headers).status_code == 403


def test_run_disabled_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", False)
    assert (
        client.post("/api/pipelines/x/runs", headers=admin_headers).status_code == 503
    )


def test_run_unknown_pipeline_returns_404(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    assert (
        client.post("/api/pipelines/no-such-id/runs", headers=admin_headers).status_code
        == 404
    )


def test_run_pipeline_without_dataset_returns_422(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    pid = client.post(
        "/api/pipelines", json={"name": "dangling"}, headers=admin_headers
    ).json()["id"]
    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 422


def _oplog_for_dataset(client, admin_headers, did):
    return [
        r
        for r in client.get("/api/ingested-records", headers=admin_headers).json()
        if r["dataset_id"] == did
    ]


def _cursor_for_pipeline(client, admin_headers, pid):
    rows = [
        c
        for c in client.get("/api/delta-cursors", headers=admin_headers).json()
        if c["pipeline_id"] == pid
    ]
    return rows[0] if rows else None


def test_first_run_lands_oplog_bootstraps_cursor_and_profiles(
    client, admin_headers, monkeypatch
):
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, did = _make_pipeline(client, admin_headers, sid)
    calls = _arm(client, admin_headers, monkeypatch, [_PAGE_1])

    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["rows_read"] == 10 and body["rows_written"] == 10
    assert body["inserts"] == 10 and body["updates"] == 0

    # first fetch is ordered by the bootstrapped cursor but unfiltered (no watermark yet)
    first_url = urllib.parse.unquote(calls[0])
    assert "$orderby=OrderDate asc" in first_url and "$filter" not in first_url

    # observable output state: op-log rows actually landed with real business keys
    oplog = _oplog_for_dataset(client, admin_headers, did)
    assert len(oplog) == 10
    assert {r["business_key"] for r in oplog} == {str(i) for i in range(10)}
    assert all(r["op"] == "insert" and r["run_id"] == body["id"] for r in oplog)

    # the cursor was bootstrapped on the temporal field and actually advanced
    cursor = _cursor_for_pipeline(client, admin_headers, pid)
    assert cursor is not None
    assert cursor["cursor_kind"] == "timestamp"
    assert cursor["cursor_value"] == "1998-05-10T00:00:00Z"
    assert cursor["last_run_id"] == body["id"]
    field_names = {
        f["id"]: f["name"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
    }
    assert field_names[cursor["cursor_field_id"]] == "OrderDate"

    # the run row is the durable record
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "succeeded" and run["rows_read"] == 10
    assert run["trigger"] == "manual" and run["finished_at"] is not None

    # §6: ingest success fired the profile + re-score pass
    assert body["profile"]["fields_profiled"] == 5
    assert body["profile"]["suggestions_rescored"] >= 1


def test_second_run_filters_from_watermark_and_advances(
    client, admin_headers, monkeypatch
):
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, did = _make_pipeline(client, admin_headers, sid)
    calls = _arm(client, admin_headers, monkeypatch, [_PAGE_1, _PAGE_2, _PAGE_2])

    client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    r2 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    body2 = r2.json()

    # the second fetch filtered strictly-later than the first run's watermark
    second_url = urllib.parse.unquote(calls[1])
    assert "$filter=OrderDate gt 1998-05-10T00:00:00Z" in second_url
    assert body2["inserts"] == 2 and body2["updates"] == 0
    assert len(_oplog_for_dataset(client, admin_headers, did)) == 12
    cursor = _cursor_for_pipeline(client, admin_headers, pid)
    assert cursor["cursor_value"] == "1998-06-02T00:00:00Z"
    assert cursor["last_run_id"] == body2["id"]

    # replaying the same page is idempotent: updates, no duplicates, watermark unchanged
    r3 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    body3 = r3.json()
    assert body3["inserts"] == 0 and body3["updates"] == 2
    assert len(_oplog_for_dataset(client, admin_headers, did)) == 12
    assert (
        _cursor_for_pipeline(client, admin_headers, pid)["cursor_value"]
        == "1998-06-02T00:00:00Z"
    )


def test_keyless_rows_are_skipped_not_written(client, admin_headers, monkeypatch):
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, did = _make_pipeline(client, admin_headers, sid)
    page = json.loads(_PAGE_1)
    page["value"].append({"OrderDate": "1998-07-01T00:00:00Z", "Freight": 1.0})
    _arm(client, admin_headers, monkeypatch, [json.dumps(page).encode()])

    body = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert body["rows_read"] == 11 and body["rows_written"] == 10
    assert body["skipped_no_key"] == 1
    assert len(_oplog_for_dataset(client, admin_headers, did)) == 10
    # a keyless row can't advance the watermark either
    assert (
        _cursor_for_pipeline(client, admin_headers, pid)["cursor_value"]
        == "1998-05-10T00:00:00Z"
    )


def test_fetch_failure_records_failed_run(client, admin_headers, monkeypatch):
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, _did = _make_pipeline(client, admin_headers, sid)
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)

    def boom(url):
        raise OSError("connection refused")

    monkeypatch.setattr("app.ingest.service._fetch_page", boom)
    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "failed"
    assert "connection refused" in body["error_detail"]
    assert "profile" not in body
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "failed" and run["finished_at"] is not None


def test_full_page_tie_is_not_lost_across_runs(client, admin_headers, monkeypatch):
    """A $top-capped page ending in a cursor-value tie must not advance the watermark past the
    cut — the tied rows beyond the cap are refetched by the next strictly-greater filter.
    """
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, did = _make_pipeline(client, admin_headers, sid)
    monkeypatch.setattr("app.ingest.service._PAGE_SIZE", 4)
    # source truth: OrderIDs 1,2 at 05-01 and 3,4,5 at 05-02. Page 1 is the first $top=4 rows —
    # FULL, and the cap cuts the 05-02 tie group (OrderID 5 is beyond the page).
    page1 = json.dumps(
        {
            "value": [
                {"OrderID": 1, "OrderDate": "1998-05-01T00:00:00Z"},
                {"OrderID": 2, "OrderDate": "1998-05-01T00:00:00Z"},
                {"OrderID": 3, "OrderDate": "1998-05-02T00:00:00Z"},
                {"OrderID": 4, "OrderDate": "1998-05-02T00:00:00Z"},
            ]
        }
    ).encode()
    # page 2: everything strictly after 05-01 — the whole tie group incl. the previously cut row
    page2 = json.dumps(
        {
            "value": [
                {"OrderID": 3, "OrderDate": "1998-05-02T00:00:00Z"},
                {"OrderID": 4, "OrderDate": "1998-05-02T00:00:00Z"},
                {"OrderID": 5, "OrderDate": "1998-05-02T00:00:00Z"},
            ]
        }
    ).encode()
    calls = _arm(client, admin_headers, monkeypatch, [page1, page2])

    b1 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert b1["status"] == "succeeded" and b1["inserts"] == 4
    # watermark stopped BELOW the possibly-cut tie
    assert (
        _cursor_for_pipeline(client, admin_headers, pid)["cursor_value"]
        == "1998-05-01T00:00:00Z"
    )

    b2 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert "OrderDate gt 1998-05-01T00:00:00Z" in urllib.parse.unquote(calls[1])
    # the row beyond the cap (OrderID 5) is recovered, the refetched tie rows just update
    assert b2["inserts"] == 1 and b2["updates"] == 2
    assert len(_oplog_for_dataset(client, admin_headers, did)) == 5
    # page 2 was not full, so the watermark now advances into the tie value
    assert (
        _cursor_for_pipeline(client, admin_headers, pid)["cursor_value"]
        == "1998-05-02T00:00:00Z"
    )


def test_poisoned_watermark_records_failed_run_not_500(
    client, admin_headers, monkeypatch
):
    """An unrenderable watermark (here: kind=numeric with a non-numeric value, reachable via the
    delta-cursor CRUD) must land ON the run as status=failed — never a 500 that leaves the run
    stuck at status='running'."""
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, _did = _make_pipeline(client, admin_headers, sid)
    order_id_field = next(
        f["id"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["name"] == "OrderID" and f["dataset_id"] == _did
    )
    client.post(
        "/api/delta-cursors",
        json={
            "name": "poisoned",
            "pipeline_id": pid,
            "cursor_field_id": order_id_field,
            "cursor_kind": "numeric",
            "cursor_value": "not-a-number",
        },
        headers=admin_headers,
    )
    _arm(client, admin_headers, monkeypatch, [_PAGE_1])

    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_detail"]
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "failed" and run["finished_at"] is not None
    # no run is ever left stuck at status='running'
    stuck = [
        x
        for x in client.get("/api/runs", headers=admin_headers).json()
        if x["pipeline_id"] == pid and x["status"] == "running"
    ]
    assert stuck == []


def test_deleted_cursor_field_degrades_without_wiping_cursor(
    client, admin_headers, monkeypatch
):
    """FK SET NULL on cursor_field_id: the next run ingests unfiltered and must NOT wipe the
    stored cursor_value / last_run_id."""
    sid = _discovered(client, admin_headers, monkeypatch)
    pid, did = _make_pipeline(client, admin_headers, sid)
    calls = _arm(client, admin_headers, monkeypatch, [_PAGE_1, _PAGE_1])

    b1 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    cursor1 = _cursor_for_pipeline(client, admin_headers, pid)
    assert cursor1["cursor_value"] == "1998-05-10T00:00:00Z"

    order_date_field = next(
        f["id"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["name"] == "OrderDate" and f["dataset_id"] == did
    )
    client.delete(f"/api/discovered-fields/{order_date_field}", headers=admin_headers)

    b2 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert b2["status"] == "succeeded"
    assert b2["updates"] == 10  # unfiltered full page, replayed idempotently
    assert "$filter" not in calls[1] and "$orderby" not in calls[1]
    cursor2 = _cursor_for_pipeline(client, admin_headers, pid)
    assert cursor2["cursor_field_id"] is None  # FK SET NULL did its thing
    assert cursor2["cursor_value"] == "1998-05-10T00:00:00Z"  # NOT wiped
    assert cursor2["last_run_id"] == b1["id"]  # NOT re-pointed


def test_dataset_without_temporal_field_full_page_ingests(
    client, admin_headers, monkeypatch
):
    """No temporal field -> no cursor bootstrap; the pipeline full-page ingests each run and
    stays idempotent through the op-log unique key."""
    sid = client.post(
        "/api/sources", json={"name": "flat", "type": "odata"}, headers=admin_headers
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={"name": "c", "endpoint": "https://svc.example/odata", "source_id": sid},
        headers=admin_headers,
    )
    did = client.post(
        "/api/datasets",
        json={"name": "Widgets", "source_id": sid},
        headers=admin_headers,
    ).json()["id"]
    client.post(
        "/api/discovered-fields",
        json={
            "name": "WidgetID",
            "data_type": "Edm.Int32",
            "is_key": True,
            "dataset_id": did,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/discovered-fields",
        json={
            "name": "Label",
            "data_type": "Edm.String",
            "is_key": False,
            "dataset_id": did,
        },
        headers=admin_headers,
    )
    pid = client.post(
        "/api/pipelines",
        json={"name": "widgets-pipe", "dataset_id": did},
        headers=admin_headers,
    ).json()["id"]
    page = json.dumps({"value": [{"WidgetID": 1, "Label": "a"}]}).encode()
    calls = _arm(client, admin_headers, monkeypatch, [page, page])

    b1 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert b1["status"] == "succeeded" and b1["inserts"] == 1
    assert "$orderby" not in calls[0] and "$filter" not in calls[0]
    assert _cursor_for_pipeline(client, admin_headers, pid) is None

    b2 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert b2["inserts"] == 0 and b2["updates"] == 1
    assert len(_oplog_for_dataset(client, admin_headers, did)) == 1
