"""Issue #664 freeform proof — one test, stubbed fetch, real Postgres.

Proves, in a single test:
* a three-page entity set (500 / 500 / 120 entries) served WITHOUT any ``@odata.nextLink`` is
  fully stored in one run — the run requests the continuations itself from the run's first page
  URL, and the second and third requests carry ``$skip=500`` / ``$skip=1000`` with the same
  ``$filter``/``$orderby`` — and the watermark reaches the one shared timestamp;
* ``INGEST_MAX_ROWS_PER_RUN=600`` stops the same set after 600 rows and the watermark stays
  unchanged (the last page was full AS SERVED, before the cap truncation — a cut);
* a served ``@odata.nextLink`` is followed in preference to the ``$skip`` continuation;
* ``build_page_url`` appends the business-key fields to ``$orderby`` after the cursor field and
  is unchanged without them;
* the cursor bootstrap picks ``LastModifiedDateTime`` given the (all temporal, in this order)
  fields ``PendingStdCostDate``, ``CreatedDateTime``, ``LastModifiedDateTime``;
* a cap of 700 on the set requests ``$skip=500`` (the SERVED count of page 1) for page 2, stops
  after 700 rows, and leaves the watermark unchanged;
* a dataset with NO key fields still pages with ``$skip`` in one run (the run logs that the
  order across pages is not guaranteed) and stores the set;
* a dataset with NO temporal field (hence NO cursor) still ``$skip``-pages past a full page
  served without a ``@odata.nextLink`` in one run and stores the set;
* a cap stop WITHOUT any ``@odata.nextLink`` on a FULL final page is a cut: the watermark
  advances only to the last fully exhausted value strictly below the cut, never to the cut
  tie value — exactly as it would with a pending nextLink.
"""

import json
import logging
import urllib.parse

from app.ingest.filters import build_page_url

ENDPOINT = "https://svc.example/odata"
T = "1998-05-01T00:00:00Z"

# One entity set whose three non-key temporal fields (in field_position order) are
# PendingStdCostDate, CreatedDateTime, LastModifiedDateTime — the bootstrap must pick the last.
_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NW" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="CostLine">
        <Key><PropertyRef Name="CostLineID"/></Key>
        <Property Name="CostLineID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="PendingStdCostDate" Type="Edm.DateTimeOffset"/>
        <Property Name="CreatedDateTime" Type="Edm.DateTimeOffset"/>
        <Property Name="LastModifiedDateTime" Type="Edm.DateTimeOffset"/>
        <Property Name="Amount" Type="Edm.Decimal"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="CostLines" EntityType="NW.CostLine"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

# One entity set with NO temporal property: the dataset gets no cursor field, so the run
# has no watermark to reason about and must drain the set with $skip alone.
_EDMX_PLAIN = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NW" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="CostLine">
        <Key><PropertyRef Name="CostLineID"/></Key>
        <Property Name="CostLineID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Amount" Type="Edm.Decimal"/>
        <Property Name="Note" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="CostLines" EntityType="NW.CostLine"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


def _plain_row(line_id):
    return {"CostLineID": line_id, "Amount": 10.0 + line_id, "Note": f"note{line_id}"}


def _row(line_id):
    return {
        "CostLineID": line_id,
        "PendingStdCostDate": T,
        "CreatedDateTime": T,
        "LastModifiedDateTime": T,
        "Amount": 10.0 + line_id,
    }


def _page(rows, next_link=None):
    body = {"value": rows}
    if next_link is not None:
        body["@odata.nextLink"] = next_link
    return json.dumps(body).encode()


def _make_pipeline(client, admin_headers, monkeypatch, tag, edmx=_EDMX):
    """A fresh OData source + connection + discovered dataset + cursor pipeline, namespaced by
    tag so the scenarios never see each other's rows. ``edmx`` swaps the discovered shape
    (the no-temporal-field scenario proves the no-cursor ``$skip`` paging)."""
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: edmx)
    sid = client.post(
        "/api/sources",
        json={"name": f"nw{tag}", "type": "odata"},
        headers=admin_headers,
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={
            "name": f"conn{tag}",
            "endpoint": ENDPOINT,
            "protocol_version": "V4",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/odata-service-configs",
        json={
            "name": f"cfg{tag}",
            "metadata_path": "$metadata",
            "default_entity_set": "CostLines",
            "source_id": sid,
        },
        headers=admin_headers,
    )
    client.post(f"/api/sources/{sid}/discover", headers=admin_headers)
    did = next(
        d["id"]
        for d in client.get("/api/datasets", headers=admin_headers).json()
        if d["source_id"] == sid
    )
    pid = client.post(
        "/api/pipelines",
        json={"name": f"pipe{tag}", "dataset_id": did, "cdc_pattern": "cursor"},
        headers=admin_headers,
    ).json()["id"]
    return pid, did


def _arm(monkeypatch, pages):
    """Enable in-API egress, queue ingest fetch payloads (recording every requested URL), and
    quiet the §6 profiler egress. Calling it again re-arms a fresh queue for the next run.
    """
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    calls = []
    queue = list(pages)

    def fake_fetch(url, timeout=30):
        calls.append(url)
        if not queue:
            raise AssertionError(f"unexpected extra fetch: {url}")
        return queue.pop(0)

    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch)
    monkeypatch.setattr(
        "app.profiling.service._fetch_rows",
        lambda url: _page([_row(1)]),
    )
    return calls


def _run(client, admin_headers, pid):
    r = client.post(f"/api/pipelines/{pid}/runs", headers=admin_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _cursor_value(client, admin_headers, pid):
    rows = [
        c
        for c in client.get("/api/delta-cursors", headers=admin_headers).json()
        if c["pipeline_id"] == pid
    ]
    assert len(rows) == 1
    return rows[0]["cursor_value"]


def _field_ids(client, admin_headers, did):
    return {
        f["name"]: f["id"]
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["dataset_id"] == did
    }


def _oplog(client, admin_headers, did):
    return [
        r
        for r in client.get("/api/ingested-records", headers=admin_headers).json()
        if r["dataset_id"] == did
    ]


def _q(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_issue664_freeform(client, admin_headers, monkeypatch, caplog):
    # --- build_page_url: keys ride $orderby after the cursor; unchanged else ---
    with_keys = build_page_url(
        ENDPOINT,
        "CostLines",
        500,
        "V4",
        "LastModifiedDateTime",
        T,
        "timestamp",
        key_fields=["CostLineID"],
    )
    q = _q(with_keys)
    assert q["$top"] == ["500"] and q["$format"] == ["json"]
    assert q["$orderby"] == ["LastModifiedDateTime asc,CostLineID asc"]
    assert q["$filter"] == [
        f"LastModifiedDateTime gt {T} or LastModifiedDateTime eq {T}"
    ]
    assert "$skip" not in q

    # without key fields the URL is unchanged from today
    plain = build_page_url(
        ENDPOINT, "CostLines", 500, "V4", "LastModifiedDateTime", T, "timestamp"
    )
    q = _q(plain)
    assert q["$orderby"] == ["LastModifiedDateTime asc"]
    assert q["$filter"] == [
        f"LastModifiedDateTime gt {T} or LastModifiedDateTime eq {T}"
    ]
    assert "$skip" not in q

    # without a cursor field the URL is unchanged — key fields never leak in
    no_cursor = build_page_url(ENDPOINT, "CostLines", 500, "V4")
    assert no_cursor == f"{ENDPOINT}/CostLines?$top=500&$format=json"
    assert (
        build_page_url(ENDPOINT, "CostLines", 500, "V4", key_fields=["CostLineID"])
        == no_cursor
    )

    # a $skip offset renders on the same page, keys in the given order
    skip_url = build_page_url(
        ENDPOINT,
        "CostLines",
        500,
        "V4",
        "LastModifiedDateTime",
        None,
        "timestamp",
        key_fields=["CostLineID", "Amount"],
        skip=1000,
    )
    q = _q(skip_url)
    assert q["$skip"] == ["1000"]
    assert q["$orderby"] == ["LastModifiedDateTime asc,CostLineID asc,Amount asc"]
    assert "$filter" not in q

    # the three-page set, every row sharing one timestamp, NO @odata.nextLink anywhere
    pages = [
        _page([_row(i) for i in range(1, 501)]),
        _page([_row(i) for i in range(501, 1001)]),
        _page([_row(i) for i in range(1001, 1121)]),
    ]

    # --- 1. three pages without any nextLink: one run stores all 1120 rows ----
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN", raising=False)
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "1")
    calls = _arm(monkeypatch, pages)
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 1120 and body["rows_written"] == 1120
    assert body["inserts"] == 1120 and body["updates"] == 0
    # exactly one fetch per page — the run requested pages 2 and 3 itself
    assert len(calls) == 3
    q0 = _q(calls[0])
    assert q0["$top"] == ["500"] and "$skip" not in q0 and "$filter" not in q0
    # bootstrap picked LastModifiedDateTime; the key field rides $orderby after it
    assert q0["$orderby"] == ["LastModifiedDateTime asc,CostLineID asc"]
    q1 = _q(calls[1])
    assert q1["$skip"] == ["500"]
    # pages 2 and 3 are the first page URL plus $skip — same $filter/$orderby/$top
    assert {k: v for k, v in q1.items() if k != "$skip"} == q0
    q2 = _q(calls[2])
    assert q2["$skip"] == ["1000"]
    assert {k: v for k, v in q2.items() if k != "$skip"} == q0
    # every row of all three pages landed, once each
    oplog = _oplog(client, admin_headers, did)
    assert len(oplog) == 1120
    assert {r["business_key"] for r in oplog} == {str(i) for i in range(1, 1121)}
    # the set was fully exhausted (last page held fewer than _PAGE_SIZE): the
    # watermark reached the one shared timestamp
    assert _cursor_value(client, admin_headers, pid) == T
    # bootstrap determinism: among PendingStdCostDate / CreatedDateTime /
    # LastModifiedDateTime (all temporal, in that field order) it picked the last
    cursors = [
        c
        for c in client.get("/api/delta-cursors", headers=admin_headers).json()
        if c["pipeline_id"] == pid
    ]
    assert len(cursors) == 1
    assert (
        cursors[0]["cursor_field_id"]
        == _field_ids(client, admin_headers, did)["LastModifiedDateTime"]
    )

    # --- 2. INGEST_MAX_ROWS_PER_RUN=600: stop after 600 rows, watermark cut ----
    # (page 2 was full AS SERVED — 500 — before the cap truncated it to 100, so the
    # run stopped on a cut page and the watermark stays unchanged)
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "600")
    pid_b, did_b = _make_pipeline(client, admin_headers, monkeypatch, "2")
    calls = _arm(monkeypatch, pages)
    body = _run(client, admin_headers, pid_b)
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 600 and body["rows_written"] == 600
    assert len(calls) == 2  # the capped page ends the run — page 3 never requested
    q1 = _q(calls[1])
    assert q1["$skip"] == ["500"]
    assert {k: v for k, v in q1.items() if k != "$skip"} == _q(calls[0])
    assert {r["business_key"] for r in _oplog(client, admin_headers, did_b)} == {
        str(i) for i in range(1, 601)
    }
    assert _cursor_value(client, admin_headers, pid_b) is None
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")

    # --- 3. a served nextLink is followed in preference to $skip --------------
    pid_c, did_c = _make_pipeline(client, admin_headers, monkeypatch, "3")
    next_link = f"{ENDPOINT}/CostLines?$continuation=2"
    calls = _arm(
        monkeypatch,
        [
            _page([_row(i) for i in range(1, 501)], next_link),
            _page([_row(i) for i in range(501, 621)]),
        ],
    )
    body = _run(client, admin_headers, pid_c)
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 620 and body["rows_written"] == 620
    assert len(calls) == 2
    # page 1 is full yet carries a nextLink: the run follows the LINK, not $skip=500
    assert calls[1] == next_link
    assert "$skip" not in _q(calls[1])
    assert _cursor_value(client, admin_headers, pid_c) == T

    # --- 4. cap 700: page 2 is $skip=500 (served count), stop at 700 rows -----
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "700")
    pid_d, did_d = _make_pipeline(client, admin_headers, monkeypatch, "4")
    calls = _arm(monkeypatch, pages)
    body = _run(client, admin_headers, pid_d)
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 700 and body["rows_written"] == 700
    assert len(calls) == 2
    q1 = _q(calls[1])
    assert q1["$skip"] == [
        "500"
    ]  # page 1 SERVED 500 entries — the offset is served, not read
    assert {k: v for k, v in q1.items() if k != "$skip"} == _q(calls[0])
    assert {r["business_key"] for r in _oplog(client, admin_headers, did_d)} == {
        str(i) for i in range(1, 701)
    }
    # page 2 was full as served at the cap: a cut, watermark unchanged
    assert _cursor_value(client, admin_headers, pid_d) is None
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")

    # --- 5. a full page of non-dict entries without a nextLink fails the run --
    # (the $skip continuation would spin forever — the nextLink loop guard, applied to
    # the self-paging path)
    pid_e, did_e = _make_pipeline(client, admin_headers, monkeypatch, "5")
    junk_page = json.dumps({"value": [f"not-a-row:{i}" for i in range(500)]}).encode()
    calls = _arm(monkeypatch, [junk_page])
    body = _run(client, admin_headers, pid_e)
    assert body["status"] == "failed", body
    assert "full page of entries" in body["error_detail"]
    assert len(calls) == 1  # the spin would have been page 2 — never requested
    assert _oplog(client, admin_headers, did_e) == []
    assert _cursor_value(client, admin_headers, pid_e) is None

    # --- 6. a keyless dataset still pages with $skip (and logs a warning) ----
    pid_f, did_f = _make_pipeline(client, admin_headers, monkeypatch, "6")
    # clear the only business key: the dataset now has NO key fields
    key_fid = _field_ids(client, admin_headers, did_f)["CostLineID"]
    r = client.put(
        f"/api/discovered-fields/{key_fid}",
        json={"is_key": False},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    calls = _arm(monkeypatch, pages)
    with caplog.at_level(logging.WARNING, logger="app.ingest.service"):
        body = _run(client, admin_headers, pid_f)
    # the keyless run does NOT fail — it pages with $skip itself and stores the set
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 1120 and body["rows_written"] == 1120
    assert len(calls) == 3
    q0f = _q(calls[0])
    # no key tie-breaker: $orderby is the cursor alone
    assert q0f["$orderby"] == ["LastModifiedDateTime asc"]
    q1f = _q(calls[1])
    assert q1f["$skip"] == ["500"]
    assert {k: v for k, v in q1f.items() if k != "$skip"} == q0f
    q2f = _q(calls[2])
    assert q2f["$skip"] == ["1000"]
    assert {k: v for k, v in q2f.items() if k != "$skip"} == q0f
    # the run logged that the order across pages is not guaranteed
    assert any(
        "order across pages is not guaranteed" in rec.message
        for rec in caplog.records
        if rec.name == "app.ingest.service"
    )
    # fully exhausted (last page short of _PAGE_SIZE): the watermark reached the
    # one shared timestamp, as in the keyed run
    assert _cursor_value(client, admin_headers, pid_f) == T

    # --- 7. a dataset with NO temporal field (no cursor) $skip-pages --------
    # a full page served WITHOUT a nextLink must NOT stop the run: with no cursor field
    # there is no tie group for the at-or-after filter to resume past, so the run
    # continues itself with $skip and drains the set in one run
    pid_g, did_g = _make_pipeline(
        client, admin_headers, monkeypatch, "7", edmx=_EDMX_PLAIN
    )
    plain_pages = [
        _page([_plain_row(i) for i in range(1, 501)]),
        _page([_plain_row(i) for i in range(501, 1001)]),
        _page([_plain_row(i) for i in range(1001, 1121)]),
    ]
    calls = _arm(monkeypatch, plain_pages)
    body = _run(client, admin_headers, pid_g)
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 1120 and body["rows_written"] == 1120
    assert len(calls) == 3  # pages 2 and 3 were requested by the run itself
    q0g = _q(calls[0])
    # no cursor field: no $filter and no $orderby — key fields never leak in either
    assert q0g["$top"] == ["500"] and "$skip" not in q0g
    assert "$orderby" not in q0g and "$filter" not in q0g
    q1g = _q(calls[1])
    assert q1g["$skip"] == ["500"]
    assert {k: v for k, v in q1g.items() if k != "$skip"} == q0g
    q2g = _q(calls[2])
    assert q2g["$skip"] == ["1000"]
    assert {k: v for k, v in q2g.items() if k != "$skip"} == q0g
    assert {r["business_key"] for r in _oplog(client, admin_headers, did_g)} == {
        str(i) for i in range(1, 1121)
    }
    # no temporal field, so no delta_cursor was ever bootstrapped
    cursors_g = [
        c
        for c in client.get("/api/delta-cursors", headers=admin_headers).json()
        if c["pipeline_id"] == pid_g
    ]
    assert cursors_g == []

    # --- 8. a cap stop WITHOUT a nextLink on a FULL final page is a cut -----
    # page 1 is one tie group at low_t; page 2 (full AS SERVED) is a tie group at
    # high_t. The cap hits mid page 2 and NO nextLink is served anywhere: the run
    # must treat the stop as a cut — the watermark advances only to the last fully
    # exhausted value (low_t), never to the cut (high_t), exactly as it would with a
    # pending nextLink
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "700")
    pid_h, did_h = _make_pipeline(client, admin_headers, monkeypatch, "8")
    low_t, high_t = "1998-06-01T00:00:00Z", "1998-06-02T00:00:00Z"

    def _row_at(line_id, ts):
        row = _row(line_id)
        row["PendingStdCostDate"] = ts
        row["CreatedDateTime"] = ts
        row["LastModifiedDateTime"] = ts
        return row

    calls = _arm(
        monkeypatch,
        [
            _page([_row_at(i, low_t) for i in range(1, 501)]),
            _page([_row_at(i, high_t) for i in range(501, 1001)]),
        ],
    )
    body = _run(client, admin_headers, pid_h)
    assert body["status"] == "succeeded", body
    assert body["rows_read"] == 700 and body["rows_written"] == 700
    assert len(calls) == 2  # the capped page ends the run
    q1h = _q(calls[1])
    assert q1h["$skip"] == ["500"]
    assert {k: v for k, v in q1h.items() if k != "$skip"} == _q(calls[0])
    assert {r["business_key"] for r in _oplog(client, admin_headers, did_h)} == {
        str(i) for i in range(1, 701)
    }
    assert _cursor_value(client, admin_headers, pid_h) == low_t
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")
