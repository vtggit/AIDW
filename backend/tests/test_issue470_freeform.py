"""Proof for issue #470 — free-form filter evaluation.

Pure pytest: no database, no HTTP. Exercises the pure evaluator in
:mod:`app.feed.filter_eval` against the AST shape produced by
:func:`app.feed.filter_parse.parse_filter`.
"""

import pytest

from app.feed.filter_eval import FilterPropertyError, evaluate
from app.feed.filter_parse import FilterError


def test_issue470_freeform():
    # FilterPropertyError is a subclass of the FilterError imported from
    # app.feed.filter_parse (never redefined).
    assert issubclass(FilterPropertyError, FilterError)

    # Basic comparison.
    assert evaluate(("cmp", "eq", "a", 1), {"a": 1}, {"a": "Edm.Int32"}) is True

    # A comparison whose property is absent from types raises
    # FilterPropertyError (naming the property).
    with pytest.raises(FilterPropertyError):
        evaluate(("cmp", "eq", "zzz", 1), {"zzz": 1}, {"a": "Edm.Int32"})

    # ------------------------------------------------------------------
    # Null semantics (types {'a': 'Edm.Int32'}).
    # ------------------------------------------------------------------
    types_int = {"a": "Edm.Int32"}
    # eq null: True on a None row value, False on 5.
    assert evaluate(("cmp", "eq", "a", None), {"a": None}, types_int) is True
    assert evaluate(("cmp", "eq", "a", None), {"a": 5}, types_int) is False
    # ne null: True on 5, False on None.
    assert evaluate(("cmp", "eq", "a", None), {"a": 5}, types_int) is False
    assert evaluate(("cmp", "ne", "a", None), {"a": 5}, types_int) is True
    assert evaluate(("cmp", "ne", "a", None), {"a": None}, types_int) is False
    # gt null and lt null on 5 are both False.
    assert evaluate(("cmp", "gt", "a", None), {"a": 5}, types_int) is False
    assert evaluate(("cmp", "lt", "a", None), {"a": 5}, types_int) is False
    # eq, ne and gt with the literal 5 on a None row value are all False.
    assert evaluate(("cmp", "eq", "a", 5), {"a": None}, types_int) is False
    assert evaluate(("cmp", "ne", "a", 5), {"a": None}, types_int) is False
    assert evaluate(("cmp", "gt", "a", 5), {"a": None}, types_int) is False

    # ------------------------------------------------------------------
    # Numeric family: all six operators, row 5 vs literals 5, 4, 6, plus
    # the str row value '5'.
    # ------------------------------------------------------------------
    for row_value in (5, "5"):
        assert evaluate(("cmp", "eq", "a", 5), {"a": row_value}, types_int) is True
        assert evaluate(("cmp", "ne", "a", 5), {"a": row_value}, types_int) is False
        assert evaluate(("cmp", "gt", "a", 4), {"a": row_value}, types_int) is True
        assert evaluate(("cmp", "ge", "a", 5), {"a": row_value}, types_int) is True
        assert evaluate(("cmp", "lt", "a", 6), {"a": row_value}, types_int) is True
        assert evaluate(("cmp", "le", "a", 5), {"a": row_value}, types_int) is True
        assert evaluate(("cmp", "gt", "a", 5), {"a": row_value}, types_int) is False
        assert evaluate(("cmp", "lt", "a", 5), {"a": row_value}, types_int) is False
        assert evaluate(("cmp", "ge", "a", 6), {"a": row_value}, types_int) is False
        assert evaluate(("cmp", "le", "a", 4), {"a": row_value}, types_int) is False

    # Numeric False cases: uncoercible row and NaN row.
    assert evaluate(("cmp", "eq", "a", 1), {"a": "abc"}, types_int) is False
    assert evaluate(("cmp", "gt", "a", 1), {"a": "abc"}, types_int) is False
    assert evaluate(("cmp", "gt", "a", 1), {"a": "NaN"}, types_int) is False

    # ------------------------------------------------------------------
    # Boolean family.
    # ------------------------------------------------------------------
    types_bool = {"a": "Edm.Boolean"}
    assert evaluate(("cmp", "eq", "a", True), {"a": True}, types_bool) is True
    assert evaluate(("cmp", "ne", "a", True), {"a": False}, types_bool) is True
    assert evaluate(("cmp", "eq", "a", False), {"a": False}, types_bool) is True
    # A string literal 'true' vs row True is False (both sides must be bool).
    assert evaluate(("cmp", "eq", "a", "true"), {"a": True}, types_bool) is False
    assert evaluate(("cmp", "gt", "a", "true"), {"a": True}, types_bool) is False

    # ------------------------------------------------------------------
    # DateTimeOffset family.
    # ------------------------------------------------------------------
    types_dt = {"a": "Edm.DateTimeOffset"}
    row_dt = {"a": "2024-01-15T00:00:00Z"}
    assert (
        evaluate(("cmp", "eq", "a", "2024-01-15T00:00:00+00:00"), row_dt, types_dt)
        is True
    )
    assert (
        evaluate(("cmp", "ne", "a", "2024-01-15T00:00:00+00:00"), row_dt, types_dt)
        is False
    )
    assert evaluate(("cmp", "gt", "a", "2024-01-14"), row_dt, types_dt) is True
    assert evaluate(("cmp", "lt", "a", "2024-01-16"), row_dt, types_dt) is True
    assert (
        evaluate(("cmp", "ge", "a", "2024-01-15T00:00:00+00:00"), row_dt, types_dt)
        is True
    )
    assert (
        evaluate(("cmp", "le", "a", "2024-01-15T00:00:00+00:00"), row_dt, types_dt)
        is True
    )
    # A row that does not parse makes the comparison False.
    assert (
        evaluate(
            ("cmp", "eq", "a", "2024-01-15T00:00:00+00:00"),
            {"a": "not-a-date"},
            types_dt,
        )
        is False
    )
    assert (
        evaluate(("cmp", "gt", "a", "2024-01-14"), {"a": "not-a-date"}, types_dt)
        is False
    )

    # ------------------------------------------------------------------
    # Lexical (string) family: all six operators.
    # ------------------------------------------------------------------
    types_str = {"a": "Edm.String"}
    assert evaluate(("cmp", "eq", "a", "abc"), {"a": "abc"}, types_str) is True
    assert evaluate(("cmp", "ne", "a", "abc"), {"a": "abd"}, types_str) is True
    assert evaluate(("cmp", "gt", "a", "abb"), {"a": "abc"}, types_str) is True
    assert evaluate(("cmp", "ge", "a", "abc"), {"a": "abc"}, types_str) is True
    assert evaluate(("cmp", "lt", "a", "abd"), {"a": "abc"}, types_str) is True
    assert evaluate(("cmp", "le", "a", "abc"), {"a": "abc"}, types_str) is True
    assert evaluate(("cmp", "gt", "a", "abc"), {"a": "abc"}, types_str) is False
    assert evaluate(("cmp", "lt", "a", "abc"), {"a": "abc"}, types_str) is False

    # ------------------------------------------------------------------
    # Composite nodes (row {'a': 1, 'b': 2, 'c': None}).
    # ------------------------------------------------------------------
    row = {"a": 1, "b": 2, "c": None}
    types = {"a": "Edm.Int32", "b": "Edm.Int32", "c": "Edm.String"}
    assert (
        evaluate(("or", ("cmp", "eq", "a", 9), ("cmp", "eq", "b", 2)), row, types)
        is True
    )
    assert (
        evaluate(("and", ("cmp", "eq", "a", 1), ("cmp", "eq", "b", 9)), row, types)
        is False
    )
    assert evaluate(("not", ("cmp", "eq", "a", 1)), row, types) is False
    assert evaluate(("not", ("cmp", "eq", "c", None)), row, types) is False
    nested = (
        "or",
        ("and", ("cmp", "eq", "a", 1), ("cmp", "gt", "b", 1)),
        ("cmp", "ne", "c", None),
    )
    assert evaluate(nested, row, types) is True

    # No short-circuit: a FilterPropertyError in either operand propagates.
    with pytest.raises(FilterPropertyError):
        evaluate(("and", ("cmp", "eq", "a", 9), ("cmp", "eq", "zzz", 1)), row, types)
    with pytest.raises(FilterPropertyError):
        evaluate(("or", ("cmp", "eq", "a", 1), ("cmp", "eq", "zzz", 1)), row, types)
