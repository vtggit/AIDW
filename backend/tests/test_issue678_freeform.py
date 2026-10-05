"""Issue #678 — freeform proof: SQL LIMIT/OFFSET pagination for the OData v4 feed.

Seeds one dataset with 2,503 payloads, sets ``FEED_PAGE_SIZE`` to 1000, and
proves, in a single node:

* AC-1 / AC-4: an unfiltered/unsorted entity-set GET is served from exactly
  ``SELECT business_key, payload FROM ingested_payloads WHERE dataset_id =
  %s ORDER BY business_key LIMIT %s OFFSET %s`` with limit = page capacity +
  1 (the page size, or ``min(page size, $top)`` when ``$top`` is given) and
  offset = ``$skip`` — the extra probe row only decides whether more rows
  remain and is never returned — and ``SELECT COUNT(*)`` runs only when
  ``$count=true``.
* AC-2 / AC-3: for each request of the matrix (no options; ``$skip=1000``;
  ``$skip=2500``; ``$skip=5000``; ``$top=10``; ``$top=1500``; ``$top=0``;
  ``$count=true`` with and without ``$skip``; ``$select`` of one property;
  ``$top=1500&$skip=1000&$count=true``) the response body is byte-for-byte
  the body expected from the seeded rows in ``business_key`` order, following
  the documented ``$top`` budget / nextLink contract (including ``$top=0``
  and the absence of a nextLink when nothing remains); following nextLinks
  from the first page yields every business key exactly once, in order; and
  no unfiltered request fetches more than page-size-plus-one payload rows
  (asserted by recording the rows the cursor returns).
"""

import base64
import hashlib
import os
import uuid
from contextlib import contextmanager
from urllib.parse import quote

import psycopg2.extras
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import feed_odata
from app.api.feed_odata import router as feed_odata_router
from app.db.connection import get_cursor

FEED_KEY = "feed-proof-key-0123456789abcdef"
PRINCIPAL = "feed-consumer"

DATASET_NAME = "Issue 678 Orders"
SET_NAME = "Issue_678_Orders"
SET_PATH = f"/api/feed/v4/{SET_NAME}"
BASE_URL = "http://testserver"
MEDIA_TYPE = "application/json;odata.metadata=minimal"

TOTAL_ROWS = 2503
PAGE_SIZE = 1000

PAGE_SQL = (
    "SELECT business_key, payload FROM ingested_payloads "
    "WHERE dataset_id = %s ORDER BY business_key "
    "LIMIT %s OFFSET %s"
)
COUNT_SQL = "SELECT COUNT(*) AS total FROM ingested_payloads WHERE dataset_id = %s"

# (business_key, payload) per row, already in business_key order.
ROWS = [
    (f"key-{index:05d}", {"Amount": index, "Label": f"row-{index}"})
    for index in range(TOTAL_ROWS)
]
ALL_KEYS = [business_key for business_key, _ in ROWS]

MATRIX = [
    {},
    {"$skip": "1000"},
    {"$skip": "2500"},
    {"$skip": "5000"},
    {"$top": "10"},
    {"$top": "1500"},
    {"$top": "0"},
    {"$count": "true"},
    {"$count": "true", "$skip": "1000"},
    {"$select": "Amount"},
    {"$top": "1500", "$skip": "1000", "$count": "true"},
]


def _basic(principal: str, key: str) -> str:
    token = base64.b64encode(f"{principal}:{key}".encode()).decode("ascii")
    return f"Basic {token}"


def _seed() -> str:
    """Insert one dataset, two fields, one feed credential, 2,503 payloads."""
    dataset_id = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (dataset_id, DATASET_NAME),
        )
        for field_name, data_type, position in (
            ("Amount", "Edm.Int32", 1),
            ("Label", "Edm.String", 2),
        ):
            cur.execute(
                "INSERT INTO discovered_fields (id, name, data_type, "
                "dataset_id, field_position, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
                (uuid.uuid4().hex, field_name, data_type, dataset_id, position),
            )
        cur.execute(
            "INSERT INTO feed_credentials (id, name, principal, key_hash, "
            "key_prefix, revoked, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                uuid.uuid4().hex,
                "Issue 678 Feed Credential",
                PRINCIPAL,
                hashlib.sha256(FEED_KEY.encode("utf-8")).hexdigest(),
                FEED_KEY[:8],
                False,
            ),
        )
        cur.executemany(
            "INSERT INTO ingested_payloads (id, name, dataset_id, "
            "business_key, payload, ingested_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
            [
                (
                    uuid.uuid4().hex,
                    "Issue 678 Payload",
                    dataset_id,
                    business_key,
                    psycopg2.extras.Json(payload),
                )
                for business_key, payload in ROWS
            ],
        )
    return dataset_id


class _CursorProbe:
    """Wrap a cursor, logging every executed statement and its fetched rows."""

    def __init__(self, cursor, log):
        self._cursor = cursor
        self._log = log
        self._last_sql = None

    def execute(self, sql, params=None):
        self._last_sql = " ".join(str(sql).split())
        if params is None:
            self._cursor.execute(sql)
        else:
            self._cursor.execute(sql, params)
        self._log.append({"sql": self._last_sql, "params": params, "rows": None})

    def fetchall(self):
        rows = self._cursor.fetchall()
        if self._last_sql is not None:
            self._log[-1]["rows"] = len(rows)
        return rows

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is not None and self._last_sql is not None:
            self._log[-1]["rows"] = 1
        return row


def _install_probe(monkeypatch, log) -> None:
    """Route every feed-odata cursor through the recording probe."""
    original = feed_odata.get_cursor

    @contextmanager
    def probing_cursor():
        with original() as cursor:
            yield _CursorProbe(cursor, log)

    monkeypatch.setattr(feed_odata, "get_cursor", probing_cursor)


def _request_facts(params: dict) -> tuple:
    skip = int(params.get("$skip", "0"))
    top = int(params["$top"]) if "$top" in params else None
    count = params.get("$count", "").lower() == "true"
    select_raw = params.get("$select")
    return skip, top, count, select_raw


def _expected_body(skip: int, top, count: bool, select_raw) -> dict:
    """The body the documented contract demands for these paging options.

    Implements the Python-side slicing reference: the page is the slice of
    the seeded rows (in business_key order) starting at ``skip`` holding
    ``min(page size, $top)`` rows (or the page size without ``$top``);
    ``@odata.count`` is the full row count when requested; the nextLink
    carries the next ``$skip``, the remaining ``$top`` budget and ``$count``
    through, and is absent when nothing remains or the budget is spent.
    """
    if top is not None:
        page = ROWS[skip : skip + min(PAGE_SIZE, top)]
    else:
        page = ROWS[skip : skip + PAGE_SIZE]
    selected = (
        None if select_raw is None else [item.strip() for item in select_raw.split(",")]
    )
    value = []
    for business_key, payload in page:
        entity = {
            "business_key": business_key,
            "Amount": payload["Amount"],
            "Label": payload["Label"],
        }
        if selected is None:
            value.append(entity)
        else:
            value.append({name: entity.get(name) for name in selected})

    body = {
        "@odata.context": f"{BASE_URL}/api/feed/v4/$metadata#{SET_NAME}",
        "value": value,
    }
    if count:
        body["@odata.count"] = TOTAL_ROWS

    if top is not None:
        more_rows = skip + len(page) < TOTAL_ROWS
        budget_left = top - len(page)
        emit_next = more_rows and budget_left > 0
        next_top = budget_left if emit_next else None
    else:
        emit_next = len(page) > 0 and skip + len(page) < TOTAL_ROWS
        next_top = None

    if emit_next:
        parts = [f"{BASE_URL}{SET_PATH}?$skip={skip + len(page)}"]
        if next_top is not None:
            parts.append(f"&$top={next_top}")
        if count:
            parts.append("&$count=true")
        if select_raw is not None:
            parts.append(f"&$select={quote(select_raw, safe=',')}")
        body["@odata.nextLink"] = "".join(parts)
    return body


def test_issue678_freeform(monkeypatch):
    # The expected nextLinks are built against the TestClient base URL, so
    # the feed must not be configured with an external base URL here.
    assert feed_odata.FEED_EXTERNAL_BASE_URL == ""
    assert not os.environ.get("FEED_EXTERNAL_BASE_URL")

    dataset_id = _seed()
    monkeypatch.setenv("FEED_PAGE_SIZE", "1000")

    app = FastAPI()
    app.include_router(feed_odata_router)
    client = TestClient(app)
    auth = {"Authorization": _basic(PRINCIPAL, FEED_KEY)}

    log: list[dict] = []
    _install_probe(monkeypatch, log)
    original_load_page = feed_odata._load_payload_page

    # --- matrix: exact bodies, exact SQL, bounded payload fetches ----------
    for params in MATRIX:
        skip, top, count, select_raw = _request_facts(params)
        log.clear()
        response = client.get(SET_PATH, headers=auth, params=params)
        assert response.status_code == 200, params
        assert response.headers["OData-Version"] == "4.0"
        assert response.headers["content-type"] == MEDIA_TYPE

        expected = _expected_body(skip, top, count, select_raw)
        assert response.json() == expected, (params, response.json(), expected)
        # Byte-for-byte: same bytes the contract body serialises to.
        assert response.content == JSONResponse(expected, media_type=MEDIA_TYPE).body

        # AC-1/AC-4: one page query with limit = capacity + 1, offset = skip.
        page_statements = [entry for entry in log if entry["sql"] == PAGE_SQL]
        assert len(page_statements) == 1, (params, log)
        capacity = PAGE_SIZE if top is None else min(PAGE_SIZE, top)
        assert page_statements[0]["params"] == (dataset_id, capacity + 1, skip)
        # AC-2: the cursor never returns more than page-size-plus-one rows,
        # and the probe row is exactly the extra one when rows remain.
        remaining = max(0, TOTAL_ROWS - skip)
        fetched = page_statements[0]["rows"]
        assert fetched == min(capacity + 1, remaining), params
        assert fetched <= PAGE_SIZE + 1

        # AC-1: COUNT(*) runs only when $count=true; the legacy full read
        # (the no-LIMIT payload select) is never issued for these requests.
        count_statements = [entry for entry in log if entry["sql"] == COUNT_SQL]
        assert (len(count_statements) == 1) == count, (params, log)
        full_reads = [
            entry
            for entry in log
            if entry["sql"].startswith(
                "SELECT business_key, payload FROM ingested_payloads"
            )
            and entry["sql"] != PAGE_SQL
        ]
        assert not full_reads, (params, full_reads)

    # --- nextLinks from the first page yield every key exactly once --------
    log.clear()
    collected: list[str] = []
    next_link = None
    pages = 0
    while True:
        pages += 1
        assert pages <= 4, "nextLink chain did not terminate"
        if next_link is None:
            response = client.get(SET_PATH, headers=auth)
        else:
            assert next_link.startswith(f"{BASE_URL}{SET_PATH}?"), next_link
            response = client.get(next_link[len(BASE_URL) :], headers=auth)
        assert response.status_code == 200
        body = response.json()
        collected.extend(entity["business_key"] for entity in body["value"])
        for entry in log:
            if entry["sql"] == PAGE_SQL:
                assert entry["rows"] <= PAGE_SIZE + 1
        log.clear()
        next_link = body.get("@odata.nextLink")
        if next_link is None:
            break
    assert collected == ALL_KEYS
    assert len(collected) == len(set(collected)) == TOTAL_ROWS
    assert pages == 3

    # --- AC-3: SQL page query vs legacy Python-side slicing, byte-for-byte -
    # The matrix plus extra budget/skip corners must return identical bytes
    # whether served from the SQL LIMIT/OFFSET page query or from the legacy
    # full-read path (forced below by disabling the page query).
    ab_cases = MATRIX + [
        {"$top": "1500", "$skip": "2500"},
        {"$top": "2503"},
        {"$top": "2503", "$count": "true"},
        {"$top": "1000", "$skip": "1000"},
        {"$select": "Label", "$count": "true"},
    ]
    sql_bodies: dict = {}
    for params in ab_cases:
        log.clear()
        response = client.get(SET_PATH, headers=auth, params=params)
        assert response.status_code == 200, params
        sql_bodies[tuple(sorted(params.items()))] = response.content

    monkeypatch.setattr(feed_odata, "_load_payload_page", lambda *args: None)
    for params in ab_cases:
        log.clear()
        response = client.get(SET_PATH, headers=auth, params=params)
        assert response.status_code == 200, params
        # The forced fallback used the legacy full read, not the page query.
        assert not [entry for entry in log if entry["sql"] == PAGE_SQL]
        assert response.content == sql_bodies[tuple(sorted(params.items()))], params

    # --- hostile inputs: no 500s, contract errors preserved ----------------
    # A $skip beyond a SQL bigint falls back to the full read: empty page,
    # no nextLink — never an error.
    response = client.get(SET_PATH, headers=auth, params={"$skip": str(2**63 + 1)})
    assert response.status_code == 200
    assert response.json()["value"] == []
    response = client.get(
        SET_PATH,
        headers=auth,
        params={"$skip": "1000000000000000000000", "$count": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == [] and body["@odata.count"] == TOTAL_ROWS
    assert "@odata.nextLink" not in body
    # Non-numeric, fractional and negative options keep their 400s.
    for bad_params in (
        {"$skip": "abc"},
        {"$skip": "-5"},
        {"$top": "abc"},
        {"$top": "-1"},
        {"$skip": "1.5"},
        {"$top": ""},
    ):
        response = client.get(SET_PATH, headers=auth, params=bad_params)
        assert response.status_code == 400, bad_params
    # Control characters and NUL bytes are rejected or harmless, never fatal.
    response = client.get(
        SET_PATH, headers=auth, params={"$filter": "business_key eq 'a\x00b'"}
    )
    assert response.status_code == 200
    assert response.json()["value"] == []
    for bad_params in ({"$select": "\x00"}, {"$orderby": "business_k\x01ey"}):
        response = client.get(SET_PATH, headers=auth, params=bad_params)
        assert response.status_code == 400, bad_params

    # --- huge $skip never fetches the dataset (no full-read fallback) ------
    # The A/B check above left the page query disabled; restore the real
    # implementation so these proofs run against it.
    monkeypatch.setattr(feed_odata, "_load_payload_page", original_load_page)

    # A $skip beyond the largest SQL OFFSET is served as an empty page
    # directly: no payload rows are fetched at all (the legacy fallback
    # would have fetched every row of the dataset), COUNT(*) only runs when
    # $count=true, and the body matches the contract — empty value, real
    # count, no nextLink.
    for huge_skip_params in (
        {"$skip": str(2**63 + 1)},
        {"$skip": "99999999999999999999", "$count": "true"},
        {"$skip": str(2**63 + 1), "$top": "10", "$count": "true"},
    ):
        log.clear()
        response = client.get(SET_PATH, headers=auth, params=huge_skip_params)
        assert response.status_code == 200, huge_skip_params
        body = response.json()
        assert body["value"] == [], huge_skip_params
        if "$count" in huge_skip_params:
            assert body["@odata.count"] == TOTAL_ROWS
        assert "@odata.nextLink" not in body, huge_skip_params
        payload_selects = [
            entry
            for entry in log
            if entry["sql"].startswith(
                "SELECT business_key, payload FROM ingested_payloads"
            )
        ]
        assert not payload_selects, (huge_skip_params, log)
        count_selects = [entry for entry in log if entry["sql"] == COUNT_SQL]
        assert len(count_selects) == (1 if "$count" in huge_skip_params else 0), (
            huge_skip_params,
            log,
        )

    # --- a field that sanitizes to business_key ----------------------------
    # A field named "business_key" sanitizes to the key property's own
    # identifier. It must be disambiguated (business_key2) instead of
    # shadowing the real key in entities, the CSDL and $filter/$select.
    collide_dataset_id = uuid.uuid4().hex
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO datasets (id, name, created_at, updated_at) "
            "VALUES (%s, %s, NOW(), NOW())",
            (collide_dataset_id, "Issue 678 Key Collide"),
        )
        for field_name, data_type, position in (
            ("business_key", "Edm.String", 1),
            ("Amount", "Edm.Int32", 2),
        ):
            cur.execute(
                "INSERT INTO discovered_fields (id, name, data_type, "
                "dataset_id, field_position, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
                (
                    uuid.uuid4().hex,
                    field_name,
                    data_type,
                    collide_dataset_id,
                    position,
                ),
            )
        cur.executemany(
            "INSERT INTO ingested_payloads (id, name, dataset_id, "
            "business_key, payload, ingested_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), NOW())",
            [
                (
                    uuid.uuid4().hex,
                    "Issue 678 Collide Payload",
                    collide_dataset_id,
                    f"real-key-{index}",
                    psycopg2.extras.Json(
                        {"business_key": f"shadow-{index}", "Amount": index}
                    ),
                )
                for index in range(3)
            ],
        )

    collide_path = "/api/feed/v4/Issue_678_Key_Collide"
    log.clear()
    response = client.get(collide_path, headers=auth)
    assert response.status_code == 200
    assert response.json()["value"] == [
        {"business_key": "real-key-0", "business_key2": "shadow-0", "Amount": 0},
        {"business_key": "real-key-1", "business_key2": "shadow-1", "Amount": 1},
        {"business_key": "real-key-2", "business_key2": "shadow-2", "Amount": 2},
    ]
    # The unfiltered read of this set came from the page query, and it
    # fetched at most page-size-plus-one rows.
    collide_page = [entry for entry in log if entry["sql"] == PAGE_SQL]
    assert len(collide_page) == 1, log
    assert collide_page[0]["rows"] <= PAGE_SIZE + 1
    # $select projects the disambiguated field, not the key property.
    response = client.get(
        collide_path, headers=auth, params={"$select": "business_key2"}
    )
    assert response.status_code == 200
    assert response.json()["value"] == [
        {"business_key2": "shadow-0"},
        {"business_key2": "shadow-1"},
        {"business_key2": "shadow-2"},
    ]
    # $filter still targets the real key property.
    response = client.get(
        collide_path,
        headers=auth,
        params={"$filter": "business_key eq 'real-key-1'"},
    )
    assert response.status_code == 200
    assert [entity["business_key"] for entity in response.json()["value"]] == [
        "real-key-1"
    ]
    # The CSDL carries exactly one business_key property per entity type:
    # the key property, plus the disambiguated field as business_key2.
    response = client.get("/api/feed/v4/$metadata", headers=auth)
    assert response.status_code == 200
    collide_type = response.text.split('<EntityType Name="Issue_678_Key_Collide">')[
        1
    ].split("</EntityType>")[0]
    assert collide_type.count('<Property Name="business_key"') == 1
    assert '<Property Name="business_key2"' in collide_type
