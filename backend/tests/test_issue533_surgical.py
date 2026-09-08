"""Proving test for issue #533: depth limit and _at_eof removal."""

import pytest

from app.feed.filter_parse import FilterSyntaxError, _Parser, parse_filter


def test_issue533_surgical():
    # --- 32 levels of parentheses still parse ---
    expr_32 = "(" * 32 + "a eq 1" + ")" * 32
    assert parse_filter(expr_32) == ("cmp", "eq", "a", 1)

    # --- 33 levels of parentheses raise FilterSyntaxError ---
    expr_33 = "(" * 33 + "a eq 1" + ")" * 33
    with pytest.raises(FilterSyntaxError):
        parse_filter(expr_33)

    # --- 500 levels deep raises FilterSyntaxError, never RecursionError ---
    expr_500 = "(" * 500 + "a eq 1" + ")" * 500
    with pytest.raises(FilterSyntaxError):
        parse_filter(expr_500)

    # --- 32 levels of 'not' still parse ---
    expr_not_32 = "not " * 32 + "a eq 1"
    result = parse_filter(expr_not_32)
    for _ in range(32):
        assert result[0] == "not"
        result = result[1]
    assert result == ("cmp", "eq", "a", 1)

    # --- 33 levels of 'not' raise FilterSyntaxError ---
    expr_not_33 = "not " * 33 + "a eq 1"
    with pytest.raises(FilterSyntaxError):
        parse_filter(expr_not_33)

    # --- _at_eof is removed ---
    assert not hasattr(_Parser, "_at_eof")

    # --- Existing expressions still parse ---
    assert parse_filter("a eq 1") == ("cmp", "eq", "a", 1)
    assert parse_filter("a eq 1 and b ne 2") == (
        "and",
        ("cmp", "eq", "a", 1),
        ("cmp", "ne", "b", 2),
    )
    assert parse_filter("not a eq 1") == ("not", ("cmp", "eq", "a", 1))
    assert parse_filter("(a eq 1) or (b eq 2)") == (
        "or",
        ("cmp", "eq", "a", 1),
        ("cmp", "eq", "b", 2),
    )
    assert parse_filter("a gt 3.14") == ("cmp", "gt", "a", 3.14)
    assert parse_filter("a eq 'hello'") == ("cmp", "eq", "a", "hello")
    assert parse_filter("a eq true") == ("cmp", "eq", "a", True)
    assert parse_filter("a eq null") == ("cmp", "eq", "a", None)
