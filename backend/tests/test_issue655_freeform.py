"""Issue #655 freeform proof — one test, stubbed fetch, real Postgres.

Proves, in a single test:
* a three-page entity set linked by ``@odata.nextLink`` is fully stored in one run;
* ``INGEST_MAX_ROWS_PER_RUN=2`` stops the run after 2 rows;
* a cross-host nextLink fails the run before that host is ever requested;
* two rows sharing the watermark timestamp, split across runs, are both stored exactly once
  (the ``ge`` filter re-reads the tie instead of skipping it);
* a failure on page 2 leaves the watermark at its previous value;
* a run stopped by the row cap part-way through the rows sharing one timestamp (a nextLink
  remains) leaves the watermark at the last fully exhausted timestamp, not at or past the
  partially read one.
* an ``&`` inside the ``$filter`` literal is percent-encoded — an unencoded ``&`` would split
  the query string into a stray parameter and break the page URL;
* a capped run whose last page yields no admissible cursor value (a keyless tail at the cap
  cut) leaves the watermark at its previous value — the cut value is unknown, so no tie group
  is provably exhausted.
"""

import json
import urllib.parse

from app.ingest.service import _max_rows_per_run

ENDPOINT = "https://svc.example/odata"

_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
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


def _row(order_id, order_date):
    return {
        "OrderID": order_id,
        "OrderDate": order_date,
        "Freight": 10.0 + order_id,
        "ShipCountry": "USA",
        "CustomerID": 100 + order_id,
    }


def _page(rows, next_link=None):
    body = {"value": rows}
    if next_link is not None:
        body["@odata.nextLink"] = next_link
    return json.dumps(body).encode()


def _make_pipeline(client, admin_headers, monkeypatch, tag):
    """A fresh OData source + connection + discovered dataset + cursor pipeline, namespaced by
    tag so the scenarios never see each other's rows."""
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: _EDMX)
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
            "default_entity_set": "Orders",
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


def _arm(client, admin_headers, monkeypatch, pages):
    """Enable in-API egress, queue ingest fetch payloads (recording every requested URL), and
    quiet the §6 profiler egress. Calling it again re-arms a fresh queue for the next run.
    """
    monkeypatch.setattr("app.api.ingest.ENABLE_INAPI_EGRESS", True)
    calls = []
    queue = list(pages)

    def fake_fetch(url):
        calls.append(url)
        if not queue:
            raise AssertionError(f"unexpected extra fetch: {url}")
        return queue.pop(0)

    monkeypatch.setattr("app.ingest.service._fetch_page", fake_fetch)
    monkeypatch.setattr(
        "app.profiling.service._fetch_rows",
        lambda url: _page([_row(1, "1998-05-01T00:00:00Z")]),
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


def _oplog(client, admin_headers, did):
    return [
        r
        for r in client.get("/api/ingested-records", headers=admin_headers).json()
        if r["dataset_id"] == did
    ]


def _unq(url):
    return urllib.parse.unquote(url)


def test_issue655_freeform(client, admin_headers, monkeypatch):
    # --- the cap is read from the environment at call time -------------------
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN", raising=False)
    assert _max_rows_per_run() == 50000  # the default
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "0")
    assert _max_rows_per_run() == 50000  # non-positive falls back to the default
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "-3")
    assert _max_rows_per_run() == 50000
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "not-a-number")
    assert _max_rows_per_run() == 50000  # non-integer falls back to the default
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "7")
    assert _max_rows_per_run() == 7  # a change takes effect on the next call
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")

    t1, t2, t3 = (
        "1998-05-01T00:00:00Z",
        "1998-05-02T00:00:00Z",
        "1998-05-03T00:00:00Z",
    )

    # --- 1. three @odata.nextLink pages, fully stored in ONE run --------------
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "1")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [
            _page(
                [_row(1, t1), _row(2, t1), _row(3, t2)], ENDPOINT + "/Orders?$page=2"
            ),
            _page([_row(4, t2), _row(5, t3)], ENDPOINT + "/Orders?$page=3"),
            _page([_row(6, t3)]),
        ],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert body["rows_read"] == 6 and body["rows_written"] == 6
    assert body["inserts"] == 6 and body["updates"] == 0
    # exactly one fetch per page; pages 2+ ARE the nextLinks (same origin as the endpoint)
    assert len(calls) == 3
    first = _unq(calls[0])
    assert first.startswith(f"{ENDPOINT}/Orders?")
    assert "$orderby=OrderDate asc" in first and "$filter" not in first
    assert _unq(calls[1]) == f"{ENDPOINT}/Orders?$page=2"
    assert _unq(calls[2]) == f"{ENDPOINT}/Orders?$page=3"
    # every row of all three pages landed, once each
    oplog = _oplog(client, admin_headers, did)
    assert len(oplog) == 6
    assert {r["business_key"] for r in oplog} == {str(i) for i in range(1, 7)}
    # the set is exhausted (last page had no nextLink): the watermark reached the last max
    assert _cursor_value(client, admin_headers, pid) == t3

    # --- 2. INGEST_MAX_ROWS_PER_RUN=2 stops the run after 2 rows --------------
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "2")
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "2")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [
            _page(
                [_row(1, t1), _row(2, t1), _row(3, t2)], ENDPOINT + "/Orders?$page=2"
            ),
            _page([_row(4, t3)]),
        ],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert body["rows_read"] == 2 and body["rows_written"] == 2
    # the cap stopped the run before the nextLink was even requested
    assert len(calls) == 1
    assert len(_oplog(client, admin_headers, did)) == 2
    # both consumed rows share t1, the cut value — nothing fully exhausted, watermark stays
    assert _cursor_value(client, admin_headers, pid) is None
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")

    # --- 3. a cross-host nextLink fails the run before that host is requested -
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "3")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [
            _page([_row(1, t1)], "https://evil.example/odata/Orders?$page=2"),
            _page([_row(2, t2)]),
        ],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "failed"
    assert "host" in body["error_detail"] and "evil.example" in body["error_detail"]
    # the cross-host page was NEVER requested
    assert len(calls) == 1
    assert not any("evil.example" in _unq(u) for u in calls)
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "failed"
    assert _cursor_value(client, admin_headers, pid) is None

    # --- 4. same-timestamp rows split across runs: both stored, once each -----
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "4")
    calls = _arm(client, admin_headers, monkeypatch, [_page([_row(1, t1)])])
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert _cursor_value(client, admin_headers, pid) == t1
    # run 2: the source gained row 2 AT THE SAME timestamp — a gt filter would skip it
    calls = _arm(client, admin_headers, monkeypatch, [_page([_row(2, t1)])])
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    # the watermark filter is ge, so the same-timestamp row is re-read, not skipped
    assert f"$filter=OrderDate gt {t1} or OrderDate eq {t1}" in _unq(calls[0])
    oplog = _oplog(client, admin_headers, did)
    assert len(oplog) == 2
    assert {r["business_key"] for r in oplog} == {"1", "2"}
    assert all(r["op"] == "insert" for r in oplog)  # stored exactly once each
    assert _cursor_value(client, admin_headers, pid) == t1

    # --- 5. a failure on page 2 leaves the watermark at its previous value ----
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "5")
    calls = _arm(client, admin_headers, monkeypatch, [_page([_row(1, t1)])])
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert _cursor_value(client, admin_headers, pid) == t1
    # run 2: page 1 is stored, page 2 dies mid-run
    flaky = []

    def flaky_fetch(url):
        flaky.append(url)
        if len(flaky) == 1:
            return _page([_row(3, t2)], ENDPOINT + "/Orders?$page=2")
        raise OSError("connection reset by peer")

    monkeypatch.setattr("app.ingest.service._fetch_page", flaky_fetch)
    body = _run(client, admin_headers, pid)
    assert body["status"] == "failed"
    assert "connection reset by peer" in body["error_detail"]
    assert len(flaky) == 2  # page 2 WAS requested — the failure is on it
    # ...but the watermark is unchanged: the advance lands only after every page is stored
    assert _cursor_value(client, admin_headers, pid) == t1
    run = client.get(f"/api/runs/{body['id']}", headers=admin_headers).json()
    assert run["status"] == "failed"
    # a later run continues from the unchanged watermark and finishes the set
    calls = _arm(client, admin_headers, monkeypatch, [_page([_row(3, t2)])])
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert f"$filter=OrderDate gt {t1} or OrderDate eq {t1}" in _unq(calls[0])
    assert _cursor_value(client, admin_headers, pid) == t2
    assert len(_oplog(client, admin_headers, did)) == 2

    # --- 6. cap stop mid-tie-group: watermark = last fully exhausted value ----
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "3")
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "6")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [
            _page(
                [
                    _row(1, t1),
                    _row(2, t1),
                    _row(3, t2),
                    _row(4, t2),
                    _row(5, t3),
                ],
                ENDPOINT + "/Orders?$page=2",
            ),
            _page([_row(6, t3)]),
        ],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert body["rows_read"] == 3  # the cap stopped the run, a nextLink remains
    assert len(calls) == 1
    # consumed: two t1 rows + one t2 row — the t2 tie group is cut. The watermark is the
    # last fully exhausted timestamp (t1), not the partially read one (t2) nor past it (t3)
    assert _cursor_value(client, admin_headers, pid) == t1
    # continuing from t1 (ge re-reads the two t1 rows as updates) exhausts the set
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [_page([_row(1, t1), _row(2, t1), _row(4, t2), _row(5, t3)])],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert f"$filter=OrderDate gt {t1} or OrderDate eq {t1}" in _unq(calls[0])
    assert body["updates"] == 2 and body["inserts"] == 2
    oplog = _oplog(client, admin_headers, did)
    assert len(oplog) == 5
    assert {r["business_key"] for r in oplog} == {str(i) for i in range(1, 6)}
    assert _cursor_value(client, admin_headers, pid) == t3

    # --- 7. capped with a valueless last page: the watermark does NOT advance --
    # (the cap cut a page that yielded no admissible cursor values — a naive
    # max-of-all-read-values would advance to t1, but the keyless row at the cut may
    # share t1 and its tie group continues past the cut)
    monkeypatch.setenv("INGEST_MAX_ROWS_PER_RUN", "2")
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "7")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [
            _page([_row(1, t1)], ENDPOINT + "/Orders?$page=2"),
            _page(
                [{"OrderDate": t1, "Freight": 9.0}, {"OrderDate": t1, "Freight": 9.0}],
                ENDPOINT + "/Orders?$page=3",
            ),
        ],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert body["rows_read"] == 2  # the keyless tail row counts against the cap
    assert body["rows_written"] == 1 and body["skipped_no_key"] == 1
    assert len(calls) == 2
    # nothing is provably fully exhausted — the watermark stays at its previous value
    assert _cursor_value(client, admin_headers, pid) is None
    # the unchanged watermark re-reads from the start (no filter) and finishes the set
    monkeypatch.delenv("INGEST_MAX_ROWS_PER_RUN")
    calls = _arm(
        client,
        admin_headers,
        monkeypatch,
        [
            _page([_row(1, t1)], ENDPOINT + "/Orders?$page=2"),
            _page(
                [{"OrderDate": t1, "Freight": 9.0}, {"OrderDate": t1, "Freight": 9.0}],
                ENDPOINT + "/Orders?$page=3",
            ),
            _page([_row(2, t2)]),
        ],
    )
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    assert "$filter" not in _unq(calls[0])
    assert _cursor_value(client, admin_headers, pid) == t2
    oplog = _oplog(client, admin_headers, did)
    assert {r["business_key"] for r in oplog} == {"1", "2"}  # keyless rows never stored

    # --- 8. a & inside the $filter literal is percent-encoded --------------------
    # (a raw & in the query string would split $filter into a stray parameter and
    # break the page; the string watermark 'A&B' comes from the hostile payload)
    pid, did = _make_pipeline(client, admin_headers, monkeypatch, "8")
    fields = {
        f["name"]: f
        for f in client.get("/api/discovered-fields", headers=admin_headers).json()
        if f["dataset_id"] == did
    }
    client.post(
        "/api/delta-cursors",
        json={
            "name": "cursor:amp",
            "pipeline_id": pid,
            "cursor_field_id": fields["ShipCountry"]["id"],
            "cursor_kind": "string",
            "cursor_value": "A&B",
        },
        headers=admin_headers,
    )
    calls = _arm(client, admin_headers, monkeypatch, [_page([_row(1, t1)])])
    body = _run(client, admin_headers, pid)
    assert body["status"] == "succeeded"
    raw_query = urllib.parse.urlparse(calls[0]).query
    assert "%26" in raw_query  # the & in the literal is encoded, never raw
    params = urllib.parse.parse_qs(raw_query)
    assert set(params) == {
        "$top",
        "$format",
        "$orderby",
        "$filter",
    }  # no stray parameter
    assert params["$filter"] == ["ShipCountry gt 'A&B' or ShipCountry eq 'A&B'"]
