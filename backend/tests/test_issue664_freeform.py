"""Issue #664 — freeform proof: client-side ``$skip`` paging when a server page carries no
``@odata.nextLink``, key-stable ``$orderby``, and the deterministic temporal bootstrap.

Proves, in a single node:

* AC-2/AC-4: ``build_page_url`` renders ``$orderby`` as cursor then business keys when key
  fields are given (``$orderby=<cursor> asc,<key1> asc,...``) and is unchanged without key
  fields (or without a cursor field); ``$skip`` is only rendered when given.
* AC-1/AC-4: a 3-page set (500 + 500 + 120 entries) served WITHOUT any
  ``@odata.nextLink``, every row sharing one timestamp, is fully stored in ONE run; the second
  and third requests carry ``$skip=500`` and ``$skip=1000`` with the same ``$filter``/``$orderby``;
  the watermark then equals that timestamp.
* AC-4: with ``INGEST_MAX_ROWS_PER_RUN=600`` the same set stops after 600 rows and the
  watermark stays unchanged; with a cap of 700 the second request is ``$skip=500`` (the served
  count), the run stops after 700 rows, and the watermark stays unchanged.
* AC-1: a served ``@odata.nextLink`` is followed in preference to ``$skip``.
* AC-3/AC-4: the bootstrap picks ``LastModifiedDateTime`` among ``PendingStdCostDate``,
  ``CreatedDateTime``, ``LastModifiedDateTime`` (all temporal, in that order); the marker
  cascade prefers ``modified`` over ``changed``.
* AC-1 wedge regression: with ``_PAGE_SIZE`` patched to 4 and a stub that honours ``$skip``,
  6 rows at T1 followed by 3 rows at T2 (pages: four T1; two T1 and two T2; one T2) are fully
  stored in ONE run with the watermark at T2, and a second run over the same data leaves the
  watermark at T2.
* Review defect 1: when the run-cap truncation of a FULL page leaves only non-dict entries
  (the served page still holds dict rows), the full-page no-dict-row guard does NOT misfire —
  the run keeps paging, stops at the cap, and the watermark lands where the read values end;
  a full page (as served) with no dict row at all still fails the run.
* Review defect 2: the ``$skip`` offset accumulates the served count of EVERY page the run
  fetched, including pages that carried a nextLink — after 500 (nextLink page) + 500 served,
  the continuation request carries ``$skip=1000`` and no row is re-read.
"""

import json
import re
import urllib.parse
from datetime import datetime, timezone

from app.db.connection import get_cursor
from app.ingest.filters import build_page_url
from app.ingest.service import _bootstrap_cursor

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

_T = "1998-05-01T00:00:00Z"
_EMPTY_PAGE = json.dumps({"value": []}).encode()


def _page_at(order_ids, ts):
    return json.dumps(
        {"value": [{"OrderID": oid, "OrderDate": ts} for oid in order_ids]}
    ).encode()


def _make_odata_source(
    client, admin_headers, name, endpoint="https://svc.example/odata"
):
    sid = client.post(
        "/api/sources", json={"name": name, "type": "odata"}, headers=admin_headers
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={
            "name": f"conn-{name}",
            "endpoint": endpoint,
            "protocol_version": "V4",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/odata-service-configs",
        json={
            "name": f"cfg-{name}",
            "metadata_path": "$metadata",
            "default_entity_set": "Orders",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    return sid


def _discovered(client, admin_headers, monkeypatch, name):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _RICH_EDMX)
    sid = _make_odata_source(client, admin_headers, name)
    r = client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    assert r.status_code == 200, r.text
    return sid


def _dataset_for_source(client, admin_headers, sid):
    return next(
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    )


def _make_pipeline(client, admin_headers, did, name):
    return client.post(
        "/api/pipelines",
        json={"name": name, "dataset_id": did, "cdc_pattern": "cursor"},
        headers=admin_headers,
    ).json()["id"]


def _arm(client, admin_headers, monkeypatch, pages):
    """Enable egress, queue ingest fetch payloads (recording URLs), quiet the profiler egress."""
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    calls = []
    queue = list(pages)

    def fake_fetch(url):
        calls.append(url)
        return queue.pop(0)

    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _EMPTY_PAGE)
    return calls


def _cursor_for_pipeline(client, admin_headers, pid):
    rows = [
        c
        for c in client.get("/api/delta-cursors", headers=admin_headers).json()
        if c["pipeline_id"] == pid
    ]
    return rows[0] if rows else None


def test_issue664_freeform(client, admin_headers, monkeypatch):
    # ------------------------------------------------------------------
    # AC-2/AC-4: build_page_url — $orderby is cursor then keys; unchanged
    # without key fields (or without a cursor field); $skip only when given.
    # ------------------------------------------------------------------
    base = "https://svc.example/odata"
    # no key fields: byte-for-byte the shape rendered before this issue
    assert urllib.parse.unquote(
        build_page_url(
            base, "Orders", 500, "V4", "OrderDate", "1998-05-10T00:00:00Z", "timestamp"
        )
    ) == (
        "https://svc.example/odata/Orders?$top=500&$format=json"
        "&$orderby=OrderDate asc"
        "&$filter=OrderDate gt 1998-05-10T00:00:00Z or OrderDate eq 1998-05-10T00:00:00Z"
    )
    # key fields: $orderby = cursor asc,key asc (stable tie order across $skip pages)
    url = build_page_url(
        base, "Orders", 500, "V4", "OrderDate", None, "timestamp", ["OrderID"]
    )
    assert "$orderby=OrderDate asc,OrderID asc" in urllib.parse.unquote(url)
    url = build_page_url(
        base, "Orders", 500, "V4", "OrderDate", None, "timestamp", ["K1", "K2"]
    )
    assert "$orderby=OrderDate asc,K1 asc,K2 asc" in urllib.parse.unquote(url)
    # no cursor field: unchanged from today even when key fields are given
    assert (
        build_page_url(base, "Orders", 500, "V4", None, None, None, ["OrderID"])
        == "https://svc.example/odata/Orders?$top=500&$format=json"
    )
    # $skip only renders when given, alongside the same $filter/$orderby/$top
    url = build_page_url(
        base,
        "Orders",
        500,
        "V4",
        "OrderDate",
        "1998-05-10T00:00:00Z",
        "timestamp",
        ["OrderID"],
        skip=500,
    )
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query["$skip"] == ["500"]
    assert query["$top"] == ["500"]
    assert query["$orderby"] == ["OrderDate asc,OrderID asc"]
    assert query["$filter"] == [
        "OrderDate gt 1998-05-10T00:00:00Z or OrderDate eq 1998-05-10T00:00:00Z"
    ]

    # ------------------------------------------------------------------
    # AC-1/AC-4: 3 pages (500/500/120) WITHOUT nextLinks, one timestamp —
    # fully stored in ONE run via $skip=500 / $skip=1000.
    # ------------------------------------------------------------------
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN", raising=False)
    sid = _discovered(client, admin_headers, monkeypatch, "iss664-a")
    did = _dataset_for_source(client, admin_headers, sid)
    pid = _make_pipeline(client, admin_headers, did, "iss664-pipe-a")
    page1 = _page_at(range(1, 501), _T)
    page2 = _page_at(range(501, 1001), _T)
    page3 = _page_at(range(1001, 1121), _T)
    calls = _arm(client, admin_headers, monkeypatch, [page1, page2, page3])

    b1 = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert b1["status"] == "succeeded", b1
    assert b1["rows_read"] == 1120 and b1["inserts"] == 1120
    # the run requested page 2 and 3 itself: $skip = entries served so far,
    # same $filter/$orderby/$top as the first page
    for idx in (0, 1, 2):
        unq = urllib.parse.unquote(calls[idx])
        assert "$orderby=OrderDate asc,OrderID asc" in unq
        assert "$filter" not in unq  # no watermark yet, same filter on every page
    assert "$skip" not in urllib.parse.unquote(calls[0])
    assert "$skip=500" in urllib.parse.unquote(calls[1])
    assert "$skip=1000" in urllib.parse.unquote(calls[2])
    assert len(calls) == 3
    # the exhausted set (short final page) advances the watermark to the one timestamp
    assert _cursor_for_pipeline(client, admin_headers, pid)["cursor_value"] == _T

    # ------------------------------------------------------------------
    # AC-4: cap 600 — stops after 600 rows, watermark unchanged (None).
    # ------------------------------------------------------------------
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "600")
    pid600 = _make_pipeline(client, admin_headers, did, "iss664-pipe-cap600")
    calls = _arm(client, admin_headers, monkeypatch, [page1, page2])
    b = client.post(f"/api/pipelines/{pid600}/runs", headers=admin_headers).json()
    assert b["status"] == "succeeded", b
    assert b["rows_read"] == 600
    assert len(calls) == 2  # page 3 is never requested
    assert _cursor_for_pipeline(client, admin_headers, pid600)["cursor_value"] is None

    # ------------------------------------------------------------------
    # AC-4: cap 700 — page 2 is $skip=500 (the SERVED count), stops after
    # 700 rows, watermark unchanged.
    # ------------------------------------------------------------------
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "700")
    pid700 = _make_pipeline(client, admin_headers, did, "iss664-pipe-cap700")
    calls = _arm(client, admin_headers, monkeypatch, [page1, page2])
    b = client.post(f"/api/pipelines/{pid700}/runs", headers=admin_headers).json()
    assert b["status"] == "succeeded", b
    assert b["rows_read"] == 700
    assert "$skip=500" in urllib.parse.unquote(calls[1])
    assert _cursor_for_pipeline(client, admin_headers, pid700)["cursor_value"] is None
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN", raising=False)

    # ------------------------------------------------------------------
    # AC-1: a served nextLink is followed in preference to $skip.
    # ------------------------------------------------------------------
    next_link = "https://svc.example/odata/Orders?$top=120&$format=json&$page=2"
    first_with_link = json.loads(page1)
    first_with_link["@odata.nextLink"] = next_link
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [json.dumps(first_with_link).encode(), page3],
    )
    b = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers).json()
    assert b["status"] == "succeeded", b
    assert b["rows_read"] == 620  # 500 from page 1, 120 from the nextLink page
    assert calls[1] == next_link  # the server link, verbatim — not a $skip URL
    assert "$skip" not in urllib.parse.unquote(calls[1])

    # ------------------------------------------------------------------
    # AC-3/AC-4: bootstrap picks LastModifiedDateTime among
    # PendingStdCostDate, CreatedDateTime, LastModifiedDateTime (all
    # temporal, in that order); the cascade prefers modified over changed.
    # ------------------------------------------------------------------
    sid2 = _make_odata_source(client, admin_headers, "iss664-b")
    did2 = client.post(
        "/api/datasets",
        json={"name": "Costs", "source_id": sid2},
        headers=admin_headers,
    ).json()["id"]
    field_ids = {}
    for position, (fname, dtype, is_key) in enumerate(
        [
            ("ProductID", "Edm.Int32", True),
            ("PendingStdCostDate", "Edm.DateTimeOffset", False),
            ("CreatedDateTime", "Edm.DateTimeOffset", False),
            ("LastModifiedDateTime", "Edm.DateTimeOffset", False),
            ("ChangedAt", "Edm.DateTimeOffset", False),
            ("ModifiedAt", "Edm.DateTimeOffset", False),
        ]
    ):
        r = client.post(
            "/api/discovered-fields",
            json={
                "name": fname,
                "data_type": dtype,
                "is_key": is_key,
                "dataset_id": did2,
                "field_position": position,
            },
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        field_ids[fname] = r.json()["id"]

    pid_b = _make_pipeline(client, admin_headers, did2, "iss664-pipe-b")
    bootstrap_fields = [
        {
            "id": field_ids[n],
            "name": n,
            "is_key": False,
            "data_type": "Edm.DateTimeOffset",
        }
        for n in ("PendingStdCostDate", "CreatedDateTime", "LastModifiedDateTime")
    ]
    with get_cursor() as cur:
        row = _bootstrap_cursor(
            cur,
            {"id": pid_b, "name": "costs"},
            bootstrap_fields,
            datetime.now(timezone.utc),
        )
    assert row is not None
    assert row["cursor_field_id"] == field_ids["LastModifiedDateTime"]
    assert row["cursor_kind"] == "timestamp" and row["cursor_value"] is None

    # cascade: "modified" outranks "changed" (and both would beat "created")
    pid_c = _make_pipeline(client, admin_headers, did2, "iss664-pipe-c")
    cascade_fields = [
        {
            "id": field_ids[n],
            "name": n,
            "is_key": False,
            "data_type": "Edm.DateTimeOffset",
        }
        for n in ("ChangedAt", "ModifiedAt")
    ]
    with get_cursor() as cur:
        row = _bootstrap_cursor(
            cur,
            {"id": pid_c, "name": "costs2"},
            cascade_fields,
            datetime.now(timezone.utc),
        )
    assert row is not None
    assert row["cursor_field_id"] == field_ids["ModifiedAt"]

    # ------------------------------------------------------------------
    # AC-1 wedge regression: _PAGE_SIZE=4, a $skip-honouring stub, 6 rows
    # at T1 then 3 at T2 (pages: 4 T1 | 2 T1 + 2 T2 | 1 T2) — fully stored
    # in ONE run with the watermark at T2; a second run leaves it at T2.
    # ------------------------------------------------------------------
    monkeypatch.setattr("app.ingest.service._PAGE_SIZE", 4)
    sid3 = _discovered(client, admin_headers, monkeypatch, "iss664-c")
    did3 = _dataset_for_source(client, admin_headers, sid3)
    pid3 = _make_pipeline(client, admin_headers, did3, "iss664-pipe-wedge")
    t1 = "1998-05-01T00:00:00Z"
    t2 = "1998-05-02T00:00:00Z"
    wedge_rows = [{"OrderID": i, "OrderDate": t1} for i in range(1, 7)] + [
        {"OrderID": i, "OrderDate": t2} for i in range(7, 10)
    ]
    calls = []

    def fake_fetch(url):
        calls.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        page_rows = wedge_rows
        match = re.search(r"OrderDate gt (\S+)", query.get("$filter", ""))
        if match:  # honour the at-or-after watermark filter
            watermark_ts = match.group(1)
            page_rows = [r for r in page_rows if r["OrderDate"] >= watermark_ts]
        skip = int(query.get("$skip", "0") or 0)
        top = int(query.get("$top", "500") or 500)
        return json.dumps({"value": page_rows[skip : skip + top]}).encode()

    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _EMPTY_PAGE)

    b1 = client.post(f"/api/pipelines/{pid3}/runs", headers=admin_headers).json()
    assert b1["status"] == "succeeded", b1
    # pages: four T1 (full) -> $skip=4 -> two T1 + two T2 (full) -> $skip=8
    # -> one T2 (not full) -> stop: the whole 9-row tie span in ONE run
    assert b1["rows_read"] == 9 and b1["inserts"] == 9
    assert "$skip=4" in urllib.parse.unquote(calls[1])
    assert "$skip=8" in urllib.parse.unquote(calls[2])
    assert "$orderby=OrderDate asc,OrderID asc" in urllib.parse.unquote(calls[1])
    assert _cursor_for_pipeline(client, admin_headers, pid3)["cursor_value"] == t2

    # second run over the same data: the at-or-after filter re-reads the T2
    # tie group (3 rows, one short page) and the watermark stays at T2
    b2 = client.post(f"/api/pipelines/{pid3}/runs", headers=admin_headers).json()
    assert b2["status"] == "succeeded", b2
    assert b2["inserts"] == 0 and b2["updates"] == 3
    assert len(calls) == 4
    assert "OrderDate gt 1998-05-02T00:00:00Z" in urllib.parse.unquote(calls[3])
    assert "$skip" not in urllib.parse.unquote(calls[3])
    assert _cursor_for_pipeline(client, admin_headers, pid3)["cursor_value"] == t2

    # ------------------------------------------------------------------
    # Review defect 1: the full-page no-dict-row guard judges the entries
    # the server SERVED, not the cap-truncated slice — when the cap
    # truncation of a full page leaves only non-dict entries but the
    # served page holds dict rows, the run must NOT fail.
    # ------------------------------------------------------------------
    monkeypatch.setattr("app.ingest.service._PAGE_SIZE", 500)
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "600")
    pid_def1 = _make_pipeline(client, admin_headers, did, "iss664-pipe-def1")
    d1_t1 = "1998-05-01T00:00:00Z"
    d1_t2 = "1998-05-02T00:00:00Z"
    # key values well clear of the rows earlier sections stored on this dataset
    d1_entries = (
        [{"OrderID": 5000 + i, "OrderDate": d1_t1} for i in range(1, 501)]
        + [f"junk-{i}" for i in range(1, 101)]
        + [{"OrderID": 5500 + i, "OrderDate": d1_t2} for i in range(1, 601)]
    )
    calls = []

    def fake_fetch_def1(url):
        calls.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        skip = int(query.get("$skip", "0") or 0)
        top = int(query.get("$top", "500") or 500)
        return json.dumps({"value": d1_entries[skip : skip + top]}).encode()

    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch_def1)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _EMPTY_PAGE)

    b = client.post(f"/api/pipelines/{pid_def1}/runs", headers=admin_headers).json()
    # page 1: 500 T1 rows (full, no nextLink) -> $skip=500. Page 2 as served:
    # 100 junk + 400 T2 rows (full) — the cap's remaining budget is 100 rows,
    # so the truncation slice is ALL JUNK. The served page still holds dict
    # rows, so the no-dict-row guard must not misfire and fail the run.
    assert b["status"] == "succeeded", b
    assert b["rows_read"] == 600 and b["inserts"] == 600
    assert len(calls) == 3
    assert (
        dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(calls[2]).query))["$skip"]
        == "1000"
    )
    # the T2 rows beyond the cap stay un-read: the watermark sits at T2 and
    # the at-or-after filter re-reads them next run
    assert (
        _cursor_for_pipeline(client, admin_headers, pid_def1)["cursor_value"] == d1_t2
    )
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN", raising=False)

    # the guard itself stays intact: a full page (as served) with no dict row
    # at all still fails the run rather than spin
    pid_def1b = _make_pipeline(client, admin_headers, did, "iss664-pipe-def1b")
    calls = []

    def fake_fetch_def1b(url):
        calls.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        int(query.get("$skip", "0") or 0)
        int(query.get("$top", "500") or 500)
        return json.dumps({"value": [f"junk-{i}" for i in range(500)]}).encode()

    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch_def1b)
    b = client.post(f"/api/pipelines/{pid_def1b}/runs", headers=admin_headers).json()
    assert b["status"] == "failed"
    assert "stopping to avoid a paging loop" in b["error_detail"]
    assert len(calls) == 1
    assert (
        _cursor_for_pipeline(client, admin_headers, pid_def1b)["cursor_value"] is None
    )

    # ------------------------------------------------------------------
    # Review defect 2: the $skip offset accumulates the served count of
    # EVERY page the run fetched, including the pages that carried a
    # nextLink — the $skip URL is the run's first page URL, i.e. the start
    # of the very same ordered stream the nextLink pages continued, so a
    # continuation that omits the nextLink pages' entries re-reads rows.
    # ------------------------------------------------------------------
    pid_def2 = _make_pipeline(client, admin_headers, did, "iss664-pipe-def2")
    # key values well clear of the rows earlier sections stored on this dataset
    d2_rows = [{"OrderID": 9000 + i, "OrderDate": _T} for i in range(1, 1121)]
    d2_next = "https://svc.example/odata/Orders?$top=500&$format=json&$skip=500"
    calls = []

    def fake_fetch_def2(url):
        calls.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        skip = int(query.get("$skip", "0") or 0)
        top = int(query.get("$top", "500") or 500)
        payload = {"value": d2_rows[skip : skip + top]}
        if "$skip" not in query:  # the server link is only offered off the first page
            payload["@odata.nextLink"] = d2_next
        return json.dumps(payload).encode()

    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch_def2)
    b = client.post(f"/api/pipelines/{pid_def2}/runs", headers=admin_headers).json()
    assert b["status"] == "succeeded", b
    assert b["rows_read"] == 1120 and b["inserts"] == 1120
    assert len(calls) == 3  # 500 (nextLink) + 500 + 120 — no re-read page
    assert calls[1] == d2_next  # the server link, verbatim
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(calls[2]).query))
    # the continuation skips everything the run already fetched: 500 + 500
    assert query["$skip"] == "1000"
    assert "$top=500" in urllib.parse.unquote(calls[2])
    assert "$orderby=OrderDate asc,OrderID asc" in urllib.parse.unquote(calls[2])
    assert "$filter" not in urllib.parse.unquote(calls[2])
    assert _cursor_for_pipeline(client, admin_headers, pid_def2)["cursor_value"] == _T
