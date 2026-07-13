"""Profiling suppression (RTBF #76): a re-profile must not resurrect an erased subject.

profile_source re-samples the LIVE source after every ingest. Without a suppression filter it
would recompute a field's min/max/most_common over the full sample — including an erased
subject's row the upstream source still holds — and repopulate exactly the value-columns the
erasure NULLed, one profiling cycle later. These tests prove profiling now drops suppressed rows
before computing VALUE stats (min/max/most_common), keeps the non-personal aggregate COUNTS
full-sample (matching the erasure/scrub convention), needs the pepper ONLY when a dataset has
suppression entries, and fails closed (rolls back, writes nothing) when entries exist but the
pepper is missing.

Lookups are scoped by the ids we create (direct DB reads) and the suppression key is derived via
the same is_key/field_position ordering the ingest filter uses, so the tests are correct
regardless of cross-test data accumulation and pin profiling's key derivation to ingest's.
"""

import json
import uuid

import pytest

# Single-key schema: OrderID is the key; City is a benign (non-PII) string field we assert on —
# cities are not flagged as PII, so their example values are retained (not NULLed by the PII seam).
_EDMX = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Demo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Order">
        <Key><PropertyRef Name="OrderID"/></Key>
        <Property Name="OrderID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="City" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Orders" EntityType="Demo.Order"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

# The erased subject (OrderID 5) is listed FIRST and holds "Zurich": the lexicographic MAX and,
# as the first-inserted distinct value, the most_common tiebreak. So on the pre-fix (unfiltered)
# code its value would surface in BOTH max_value and most_common_value; dropping it moves max to
# "Delhi" and most_common to "Amsterdam" (the first kept row), while a kept subject holds the MIN.
_ROWS = [
    {"OrderID": 5, "City": "Zurich"},
    {"OrderID": 1, "City": "Amsterdam"},
    {"OrderID": 2, "City": "Berlin"},
    {"OrderID": 3, "City": "Cairo"},
    {"OrderID": 4, "City": "Delhi"},
]
_ROWS_JSON = json.dumps({"value": _ROWS}).encode()

# Composite-key schema: OrderID + LineID. OrderID is DECLARED FIRST (lower field_position) but
# sorts AFTER LineID alphabetically — so the business_key concatenation order ("OrderID|LineID")
# is only correct if profiling honours field_position, not name. This pins parity with ingest.
_EDMX_COMPOSITE = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Demo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Line">
        <Key><PropertyRef Name="OrderID"/><PropertyRef Name="LineID"/></Key>
        <Property Name="OrderID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="LineID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="City" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="C">
        <EntitySet Name="Lines" EntityType="Demo.Line"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

# The erased subject is (OrderID 5, LineID 2) holding "Zurich" (the max). Its NEAR-TWIN
# (OrderID 5, LineID 3, "Amsterdam") shares OrderID but differs in LineID and must be RETAINED —
# proving the filter matches the FULL composite key, not just OrderID.
_ROWS_COMPOSITE = [
    {"OrderID": 5, "LineID": 2, "City": "Zurich"},
    {"OrderID": 5, "LineID": 3, "City": "Amsterdam"},
    {"OrderID": 1, "LineID": 9, "City": "Berlin"},
]
_ROWS_COMPOSITE_JSON = json.dumps({"value": _ROWS_COMPOSITE}).encode()

PEPPER = "profiling-fixture-pepper"


def _make_source(client, admin_headers):
    sid = client.post(
        "/api/sources",
        json={"name": f"prof-suppr-{uuid.uuid4().hex[:8]}", "type": "odata"},
        headers=admin_headers,
    ).json()["id"]
    client.post(
        "/api/source-connections",
        json={"name": "c", "endpoint": "https://svc.example/odata", "source_id": sid},
        headers=admin_headers,
    )
    return sid


def _discover(client, admin_headers, monkeypatch, sid, edmx):
    monkeypatch.setattr("app.api.discovery.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.discovery.service._fetch_metadata", lambda url: edmx)
    return client.post(f"/api/sources/{sid}/discover", headers=admin_headers).json()


def _profile(client, admin_headers, monkeypatch, sid, rows_json):
    monkeypatch.setattr("app.api.profiling.ENABLE_INAPI_EGRESS", True)
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: rows_json)
    return client.post(f"/api/sources/{sid}/profile", headers=admin_headers).json()


def _dataset_id(sid):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT id FROM datasets WHERE source_id = %s", (sid,))
        return cur.fetchone()["id"]


def _field_id(ds, name):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM discovered_fields WHERE dataset_id = %s AND name = %s",
            (ds, name),
        )
        return cur.fetchone()["id"]


def _profile_row(field_id):
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM field_profiles WHERE discovered_field_id = %s", (field_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _business_key_of(ds, row):
    """The row's business_key using the SAME is_key/field_position ordering ingest uses — so the
    suppressed hash matches what ingest/erasure would record, and the test pins profiling to it.
    """
    from app.db.connection import get_cursor
    from app.ingest.mapper import business_key

    with get_cursor() as cur:
        cur.execute(
            "SELECT name FROM discovered_fields WHERE dataset_id = %s AND is_key "
            "ORDER BY field_position NULLS LAST, name",
            (ds,),
        )
        key_names = [r["name"] for r in cur.fetchall()]
    return business_key(row, key_names)


def _suppress(ds, key):
    from app.db.connection import get_cursor
    from app.governance.hashing import subject_key_hash

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO suppression_entries (id, name, key_hash, dataset_id) "
            "VALUES (%s, 'suppr', %s, %s) ON CONFLICT (key_hash) DO NOTHING",
            (uuid.uuid4().hex, subject_key_hash(ds, key), ds),
        )


def test_profiling_drops_suppressed_subject_from_stats(
    client, admin_headers, monkeypatch
):
    """Erased subject absent from the value columns; non-personal counts stay full-sample."""
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid, _EDMX)
    ds = _dataset_id(sid)
    _suppress(ds, _business_key_of(ds, _ROWS[0]))  # erase OrderID 5 ("Zurich")

    _profile(client, admin_headers, monkeypatch, sid, _ROWS_JSON)

    city = _profile_row(_field_id(ds, "City"))
    assert city is not None
    # VALUE columns exclude the erased subject ("Zurich" was both the max and the most_common)
    assert city["max_value"] == "Delhi"
    assert city["min_value"] == "Amsterdam"
    assert city["most_common_value"] == "Amsterdam"
    assert "Zurich" not in {
        city["min_value"],
        city["max_value"],
        city["most_common_value"],
    }
    # COUNTS stay full-sample (non-personal aggregates, kept — matches the erasure convention)
    assert city["row_count"] == 5
    assert city["distinct_count"] == 5


def test_profiling_needs_no_pepper_when_nothing_suppressed(
    client, admin_headers, monkeypatch
):
    """No suppression entries -> profiling never resolves the pepper (lazy skip)."""
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER", raising=False)
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid, _EDMX)

    _profile(client, admin_headers, monkeypatch, sid, _ROWS_JSON)  # must not raise

    city = _profile_row(_field_id(_dataset_id(sid), "City"))
    assert city is not None
    assert city["max_value"] == "Zurich"  # full sample, erased subject included
    assert city["row_count"] == 5


def test_profiling_fails_closed_and_rolls_back_without_pepper(
    client, admin_headers, monkeypatch
):
    """Entries exist but the pepper is missing: profiling raises and the transaction rolls back,
    leaving the prior profile untouched — no silent re-profiling of the erased subject.
    """
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid, _EDMX)
    ds = _dataset_id(sid)

    # baseline profile (no suppression yet): the City row exists with the full-sample max
    _profile(client, admin_headers, monkeypatch, sid, _ROWS_JSON)
    assert _profile_row(_field_id(ds, "City"))["max_value"] == "Zurich"

    _suppress(ds, _business_key_of(ds, _ROWS[0]))
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER")
    monkeypatch.setattr("app.profiling.service._fetch_rows", lambda url: _ROWS_JSON)
    from app.profiling.service import profile_source

    with pytest.raises(RuntimeError, match="AIDW_SUPPRESSION_PEPPER"):
        profile_source(sid)

    # rollback: the pre-existing profile row is UNCHANGED (not deleted, not re-computed)
    assert _profile_row(_field_id(ds, "City"))["max_value"] == "Zurich"


def test_profiling_drops_suppressed_composite_key_subject(
    client, admin_headers, monkeypatch
):
    """Composite key (OrderID+LineID): the erased subject is dropped only if profiling concatenates
    key fields in field_position order (matching ingest); its near-twin sharing OrderID is kept.
    """
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    sid = _make_source(client, admin_headers)
    _discover(client, admin_headers, monkeypatch, sid, _EDMX_COMPOSITE)
    ds = _dataset_id(sid)
    _suppress(
        ds, _business_key_of(ds, _ROWS_COMPOSITE[0])
    )  # erase (OrderID 5, LineID 2)

    _profile(client, admin_headers, monkeypatch, sid, _ROWS_COMPOSITE_JSON)

    city = _profile_row(_field_id(ds, "City"))
    assert city is not None
    assert "Zurich" not in {
        city["min_value"],
        city["max_value"],
        city["most_common_value"],
    }
    assert city["max_value"] == "Berlin"  # erased subject's "Zurich" gone
    assert (
        city["min_value"] == "Amsterdam"
    )  # near-twin (5, 3) RETAINED — full key matched
    assert city["row_count"] == 3  # counts stay full-sample
