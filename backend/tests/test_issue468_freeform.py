"""Proving test for issue #468 — free-form filter expression parser.

Pure pytest: no database rows, no HTTP. Imports ``parse_filter``,
``FilterError`` and ``FilterSyntaxError`` from ``app.feed.filter_parse`` and
asserts the grammar, literal kinds, boolean composition, and error behavior.
"""

import pytest

from app.feed.filter_parse import FilterError, FilterSyntaxError, parse_filter


def test_issue468_freeform():
    # --- Exception hierarchy ------------------------------------------------
    assert issubclass(FilterSyntaxError, FilterError)
    assert issubclass(FilterError, Exception)

    # --- Basic comparison ---------------------------------------------------
    assert parse_filter("a eq 1") == ("cmp", "eq", "a", 1)

    # --- Each of the six operators ------------------------------------------
    assert parse_filter("a eq 1") == ("cmp", "eq", "a", 1)
    assert parse_filter("a ne 1") == ("cmp", "ne", "a", 1)
    assert parse_filter("a gt 1") == ("cmp", "gt", "a", 1)
    assert parse_filter("a ge 1") == ("cmp", "ge", "a", 1)
    assert parse_filter("a lt 1") == ("cmp", "lt", "a", 1)
    assert parse_filter("a le 1") == ("cmp", "le", "a", 1)

    # --- Properties kept verbatim (case preserved) --------------------------
    assert parse_filter("Order_Id gt 1") == ("cmp", "gt", "Order_Id", 1)

    # --- Literal kinds ------------------------------------------------------
    # Single-quoted string with '' as the escaped quote.
    assert parse_filter("name eq 'it''s'") == ("cmp", "eq", "name", "it's")
    # Decimal -> float.
    assert parse_filter("a eq 1.5") == ("cmp", "eq", "a", 1.5)
    # true / false -> bool (checked with `is`, so int 1/0 does not pass).
    assert parse_filter("a eq true")[3] is True
    assert parse_filter("a eq false")[3] is False
    # null -> None.
    assert parse_filter("a eq null")[3] is None
    # Integer literal is an int and not a bool.
    int_literal = parse_filter("a eq 1")[3]
    assert isinstance(int_literal, int)
    assert not isinstance(int_literal, bool)
    # Unquoted ISO 8601 date / datetime -> str verbatim.
    assert parse_filter("d lt 2024-01-02T00:00:00Z") == (
        "cmp",
        "lt",
        "d",
        "2024-01-02T00:00:00Z",
    )
    assert parse_filter("d ge 2024-01-02") == ("cmp", "ge", "d", "2024-01-02")

    # --- Boolean composition: precedence ------------------------------------
    assert parse_filter("a eq 1 or b eq 2 and not c eq 3") == (
        "or",
        ("cmp", "eq", "a", 1),
        (
            "and",
            ("cmp", "eq", "b", 2),
            ("not", ("cmp", "eq", "c", 3)),
        ),
    )

    # --- Parenthesised override ---------------------------------------------
    assert parse_filter("(a eq 1 or b eq 2) and not c eq 3") == (
        "and",
        (
            "or",
            ("cmp", "eq", "a", 1),
            ("cmp", "eq", "b", 2),
        ),
        ("not", ("cmp", "eq", "c", 3)),
    )

    # --- Left-associative chain ---------------------------------------------
    assert parse_filter("a eq 1 and b eq 2 and c eq 3") == (
        "and",
        (
            "and",
            ("cmp", "eq", "a", 1),
            ("cmp", "eq", "b", 2),
        ),
        ("cmp", "eq", "c", 3),
    )

    # --- Case-insensitive keywords and operators ----------------------------
    assert parse_filter("A EQ 1 AND B NE 2") == (
        "and",
        ("cmp", "eq", "A", 1),
        ("cmp", "ne", "B", 2),
    )

    # --- Anything outside the grammar raises FilterSyntaxError --------------
    # Function call.
    with pytest.raises(FilterSyntaxError) as exc1:
        parse_filter("contains(a, 1)")
    msg1 = str(exc1.value)
    assert "contains" in msg1 or "(" in msg1 or "," in msg1

    # Arithmetic.
    with pytest.raises(FilterSyntaxError) as exc2:
        parse_filter("a eq 1 + 2")
    assert "+" in str(exc2.value)

    # Unbalanced parenthesis (ends early).
    with pytest.raises(FilterSyntaxError) as exc3:
        parse_filter("(a eq 1")
    assert "end of input" in str(exc3.value)

    # Trailing token after a complete expression.
    with pytest.raises(FilterSyntaxError) as exc4:
        parse_filter("a eq 1 extra")
    assert "extra" in str(exc4.value)

    # Empty expression (ends early).
    with pytest.raises(FilterSyntaxError) as exc5:
        parse_filter("")
    assert "end of input" in str(exc5.value)

    # Whitespace-only expression (ends early).
    with pytest.raises(FilterSyntaxError) as exc6:
        parse_filter(" ")
    assert "end of input" in str(exc6.value)
