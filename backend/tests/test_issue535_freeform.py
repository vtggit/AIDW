"""Proving test for issue #535.

Two root-cause fixes are proven here:

1. ``_coerce_sort_value`` for ``Edm.Boolean`` returns the value only when it is a
   JSON boolean and ``None`` otherwise — the same "not a boolean, no ordering" rule
   ``filter_eval`` applies — so the string ``"false"`` no longer sorts as ``True`` and
   ``$orderby`` on a boolean property agrees with ``$filter``. The sort itself keeps
   no-ordering values LAST in both ascending and descending order (a descending sort
   must not float the no-ordering rows to the front).

2. Collision suffixes in entity-set naming are applied within the 128-character
   identifier cap: when the base is too long for the suffix, the base is shortened so
   the suffixed identifier is at most 128 characters and remains unique across the set.
"""

from app.api.feed_odata import _coerce_sort_value, _sort_entities
from app.feed.filter_eval import evaluate
from app.feed.filter_parse import parse_filter
from app.feed.naming import entity_set_names


def _boolean_sort_entities() -> list[dict]:
    """Rows covering JSON booleans, boolean-looking strings, and null."""
    return [
        {"business_key": "k1", "active": True},
        {"business_key": "k2", "active": False},
        {"business_key": "k3", "active": "false"},
        {"business_key": "k4", "active": "true"},
        {"business_key": "k5", "active": None},
    ]


def _boolean_fields() -> list[dict]:
    return [{"name": "active", "data_type": "Edm.Boolean"}]


def test_issue535_freeform():
    # ------------------------------------------------------------------
    # Part 1a: _coerce_sort_value for Edm.Boolean — JSON booleans only.
    # ------------------------------------------------------------------
    assert _coerce_sort_value(True, "Edm.Boolean") is True
    assert _coerce_sort_value(False, "Edm.Boolean") is False
    # Non-boolean values (including the strings "true"/"false") have no ordering.
    assert _coerce_sort_value("false", "Edm.Boolean") is None
    assert _coerce_sort_value("true", "Edm.Boolean") is None
    assert _coerce_sort_value(None, "Edm.Boolean") is None
    assert _coerce_sort_value(0, "Edm.Boolean") is None
    assert _coerce_sort_value(1, "Edm.Boolean") is None

    # ------------------------------------------------------------------
    # Part 1b: $orderby agrees with $filter — the strings "true"/"false" are
    # not booleans, so $filter never matches them and $orderby treats them
    # as no-ordering (None), not as True/False.
    # ------------------------------------------------------------------
    types = {"active": "Edm.Boolean"}
    for value in ("true", "false"):
        row = {"active": value}
        assert evaluate(parse_filter("active eq true"), row, types) is False
        assert evaluate(parse_filter("active eq false"), row, types) is False
        assert _coerce_sort_value(value, "Edm.Boolean") is None

    # ------------------------------------------------------------------
    # Part 1c: the sort keeps no-ordering values LAST in both directions.
    # ------------------------------------------------------------------
    fields = _boolean_fields()
    entities = _boolean_sort_entities()

    asc = _sort_entities(entities, [("active", False)], fields)
    assert [e["business_key"] for e in asc] == ["k2", "k1", "k3", "k4", "k5"]

    # Descending: True first, then False, then the no-ordering rows (never first).
    desc = _sort_entities(entities, [("active", True)], fields)
    assert [e["business_key"] for e in desc] == ["k1", "k2", "k3", "k4", "k5"]

    # ------------------------------------------------------------------
    # Part 2: collision suffixes stay within the 128-character cap.
    # ------------------------------------------------------------------
    long_name = "x" * 130
    base = "x" * 128  # odata_identifier caps the base to 128 chars
    datasets = [
        {"id": "a", "name": long_name, "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "b", "name": long_name, "created_at": "2024-01-02T00:00:00+00:00"},
        {"id": "c", "name": long_name, "created_at": "2024-01-03T00:00:00+00:00"},
    ]
    sets = entity_set_names(datasets)

    assert len(sets) == 3
    assert len(set(sets)) == 3
    assert set(sets.values()) == {"a", "b", "c"}
    for name in sets:
        assert len(name) <= 128, (name, len(name))

    # Earliest keeps the bare (capped) name; later ones are suffixed within the cap.
    assert sets[base] == "a"
    assert sets[base[:126] + "_2"] == "b"
    assert sets[base[:126] + "_3"] == "c"
    assert len(base[:126] + "_2") == 128
    assert len(base[:126] + "_3") == 128

    # Short-name collisions still suffix normally (the base fits under the cap).
    short = [
        {"id": "a", "name": "Orders", "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "b", "name": "Orders", "created_at": "2024-01-02T00:00:00+00:00"},
    ]
    short_sets = entity_set_names(short)
    assert short_sets["Orders"] == "a"
    assert short_sets["Orders_2"] == "b"
