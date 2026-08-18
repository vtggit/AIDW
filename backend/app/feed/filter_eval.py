"""Free-form filter expression evaluator for the feed surface.

Pure, dependency-free evaluator that walks the nested-tuple AST produced by
:func:`app.feed.filter_parse.parse_filter` and decides whether a single row
satisfies it. No database, no I/O — the feed service calls :func:`evaluate`
per row with the row's values and the OData property types as advertised by
``$metadata``.

AST nodes (see :mod:`app.feed.filter_parse`):

    comparison  -> ("cmp", op, property, literal)
    and         -> ("and", left, right)
    or          -> ("or", left, right)
    not         -> ("not", operand)

``op`` is one of ``eq ne gt ge lt le``. ``literal`` is a Python ``str``,
``int``, ``float``, ``bool`` or ``None`` (the null literal). ``types`` maps
each OData property name (verbatim, as ``$metadata`` advertises it) to its
``Edm`` type string. The row value is read as ``row.get(property)`` with the
property taken verbatim from the AST.

Semantics:

* A comparison whose property is absent from ``types`` raises
  :class:`FilterPropertyError` (a :class:`FilterError`) naming the property,
  before any null or type handling.
* Null rules (before any type-family comparison): a null literal makes ``eq``
  true exactly when the row value is ``None`` and ``ne`` true exactly when it
  is not, while ``gt ge lt le`` against the null literal are always false; a
  ``None`` row value with a non-null literal is false for every operator,
  ``ne`` included.
* Otherwise the comparison is made by the type family of ``types[property]``:
  numeric Edm types compare numerically (both sides coerced with
  ``decimal.Decimal(str(x))``; a side that cannot be coerced, or that coerces
  to NaN, makes the comparison false); ``Edm.Boolean`` compares as Python bool
  (both sides must be bool, otherwise false); ``Edm.DateTimeOffset`` and
  ``Edm.Date`` parse both sides with ``datetime.datetime.fromisoformat`` after
  ``str(x)`` (a trailing ``Z`` becomes ``+00:00`` and a date-only value gets
  ``T00:00:00+00:00`` appended; a side that does not parse makes the
  comparison false; a parsed value with no UTC offset is treated as UTC);
  every other Edm type compares lexically on ``str(row value)`` versus
  ``str(literal)``.
* Composite nodes recurse with Python truth on the recursive results and
  always return a bool. Both operands of ``and`` and ``or`` are always
  evaluated (no short-circuit), so a :class:`FilterPropertyError` raised by
  any nested comparison propagates whatever the other operand's value.
"""

from __future__ import annotations

import datetime
import decimal

from app.feed.filter_parse import FilterError

# Edm types that compare numerically.
_NUMERIC_TYPES = frozenset(
    {
        "Edm.Int16",
        "Edm.Int32",
        "Edm.Int64",
        "Edm.Byte",
        "Edm.SByte",
        "Edm.Decimal",
        "Edm.Double",
        "Edm.Single",
    }
)

# Edm types that compare as booleans.
_BOOLEAN_TYPES = frozenset({"Edm.Boolean"})

# Edm types that compare as parsed datetimes.
_DATETIME_TYPES = frozenset({"Edm.DateTimeOffset", "Edm.Date"})

# Map each comparison operator to its Python comparison function.
_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
}


class FilterPropertyError(FilterError):
    """A comparison referenced a property that is not in the type map.

    The message names the offending property.
    """


def _coerce_decimal(value: object) -> decimal.Decimal | None:
    """Coerce ``value`` to a ``Decimal`` via ``str``; ``None`` when impossible or NaN."""
    try:
        dec = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, ValueError, TypeError):
        return None
    if dec.is_nan():
        return None
    return dec


def _coerce_datetime(value: object) -> datetime.datetime | None:
    """Parse ``value`` as an ISO 8601 datetime; ``None`` when it does not parse.

    A trailing ``Z`` is replaced with ``+00:00`` and a date-only value
    (``YYYY-MM-DD``) gets ``T00:00:00+00:00`` appended. A parsed value with no
    UTC offset is treated as UTC.
    """
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = text + "T00:00:00+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _compare(op: str, row_value: object, literal: object, edm_type: str) -> bool:
    """Compare a non-null row value against a non-null literal by type family."""
    if edm_type in _NUMERIC_TYPES:
        left = _coerce_decimal(row_value)
        right = _coerce_decimal(literal)
        if left is None or right is None:
            return False
        return bool(_OPS[op](left, right))
    if edm_type in _BOOLEAN_TYPES:
        if not isinstance(row_value, bool) or not isinstance(literal, bool):
            return False
        return bool(_OPS[op](row_value, literal))
    if edm_type in _DATETIME_TYPES:
        left = _coerce_datetime(row_value)
        right = _coerce_datetime(literal)
        if left is None or right is None:
            return False
        return bool(_OPS[op](left, right))
    # Every other Edm type compares lexically on the string projection.
    return bool(_OPS[op](str(row_value), str(literal)))


def _evaluate_cmp(
    op: str, property: str, literal: object, row: dict, types: dict
) -> bool:
    """Evaluate a single comparison node."""
    if property not in types:
        raise FilterPropertyError(f"unknown property '{property}' in filter expression")
    row_value = row.get(property)
    # Null rules apply before any type-family comparison.
    if literal is None:
        if op == "eq":
            return row_value is None
        if op == "ne":
            return row_value is not None
        return False
    if row_value is None:
        return False
    return _compare(op, row_value, literal, types[property])


def evaluate(ast: tuple, row: dict, types: dict[str, str]) -> bool:
    """Evaluate a parsed filter AST against a single row.

    Returns exactly ``True`` or ``False``. Raises :class:`FilterPropertyError`
    (a :class:`FilterError`) when a comparison references a property absent
    from ``types``.
    """
    node = ast
    kind = node[0]
    if kind == "cmp":
        _, op, property, literal = node
        return _evaluate_cmp(op, property, literal, row, types)
    if kind == "and":
        # Both operands are always evaluated (no short-circuit).
        left = evaluate(node[1], row, types)
        right = evaluate(node[2], row, types)
        return bool(left and right)
    if kind == "or":
        # Both operands are always evaluated (no short-circuit).
        left = evaluate(node[1], row, types)
        right = evaluate(node[2], row, types)
        return bool(left or right)
    if kind == "not":
        return not evaluate(node[1], row, types)
    raise FilterError(f"unknown filter AST node {kind!r}")
