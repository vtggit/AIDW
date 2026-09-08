"""Proving test for issue #514: signed numeric literals in $filter."""

from app.feed.filter_parse import parse_filter


def test_issue514_surgical():
    # Signed integer: amount lt -5
    ast = parse_filter("amount lt -5")
    assert ast == ("cmp", "lt", "amount", -5)

    # Signed decimal: amount lt -5.0
    ast = parse_filter("amount lt -5.0")
    assert ast == ("cmp", "lt", "amount", -5.0)

    # Positive sign: amount gt +5
    ast = parse_filter("amount gt +5")
    assert ast == ("cmp", "gt", "amount", 5)

    # Previously-working non-negative integer filter still parses
    ast = parse_filter("amount gt 5")
    assert ast == ("cmp", "gt", "amount", 5)

    # Previously-working non-negative decimal filter still parses
    ast = parse_filter("amount lt 3.14")
    assert ast == ("cmp", "lt", "amount", 3.14)
