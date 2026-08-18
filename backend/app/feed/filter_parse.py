"""Free-form filter expression parser for the feed surface.

Pure, dependency-free parser that turns a free-form filter string (the kind
a spreadsheet OData client folds into a ``$filter``) into a nested-tuple AST.
No database, no I/O — the feed service calls :func:`parse_filter` to build a
stable, inspectable tree it can later evaluate.

Grammar (case-insensitive keywords and operators, left-associative chains):

    expression  := or_expr
    or_expr     := and_expr ( "or" and_expr )*
    and_expr    := not_expr ( "and" not_expr )*
    not_expr    := "not" not_expr | comparison
    comparison  := property op literal
    op          := "eq" | "ne" | "gt" | "ge" | "lt" | "le"
    property    := [A-Za-z_][A-Za-z0-9_]*
    literal     := string | integer | decimal | true | false | null | date

Rendered AST nodes:

    comparison  -> ("cmp", op, property, literal)
    and         -> ("and", left, right)
    or          -> ("or", left, right)
    not         -> ("not", operand)

Properties are kept verbatim (case preserved, never normalised). Operators
and keywords are matched case-insensitively and rendered lower-case.
"""

from __future__ import annotations

import re

# Operators a comparison may use, in the order they are tried.
_COMPARISON_OPS = ("eq", "ne", "gt", "ge", "lt", "le")

# Boolean keywords, matched case-insensitively.
_AND = "and"
_OR = "or"
_NOT = "not"

# A property is an identifier: a letter or underscore, then letters, digits
# or underscores.
_PROPERTY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# An integer literal (optionally signed).
_INT_RE = re.compile(r"[+-]?\d+")

# A decimal literal (optionally signed, with a fractional part).
_DECIMAL_RE = re.compile(r"[+-]?\d+\.\d+")

# An unquoted ISO 8601 date or datetime: four digits then a hyphen, read to
# the next whitespace, parenthesis or end. Kept verbatim as a string.
_DATE_RE = re.compile(r"\d{4}-")


class FilterError(Exception):
    """Base error for free-form filter parsing and evaluation."""


class FilterSyntaxError(FilterError):
    """The filter text is not valid filter grammar.

    The message names the offending token text (or the phrase ``end of
    input`` when the expression ends early).
    """


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Split ``text`` into ``(kind, value)`` tokens.

    Kinds: ``"ident"`` (property or keyword), ``"string"``, ``"number"``,
    ``"date"``, ``"lparen"``, ``"rparen"``, ``"op"`` (comparison operator),
    ``"eof"``. Anything else raises :class:`FilterSyntaxError` naming the
    offending character.
    """
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "(":
            tokens.append(("lparen", ch))
            i += 1
            continue
        if ch == ")":
            tokens.append(("rparen", ch))
            i += 1
            continue
        if ch == "'":
            # Single-quoted string; '' is the escaped quote.
            i += 1
            buf: list[str] = []
            while i < n:
                c = text[i]
                if c == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        buf.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(c)
                i += 1
            else:
                raise FilterSyntaxError(
                    "unterminated string literal in filter expression"
                )
            tokens.append(("string", "".join(buf)))
            continue
        if ch.isdigit():
            # Could be a date (four digits then a hyphen) or a number.
            if _DATE_RE.match(text, i):
                # Read to the next whitespace, parenthesis or end.
                j = i
                while j < n and not text[j].isspace() and text[j] not in "()":
                    j += 1
                tokens.append(("date", text[i:j]))
                i = j
                continue
            # Number: integer or decimal.
            m = _DECIMAL_RE.match(text, i)
            if m:
                tokens.append(("number", m.group(0)))
                i = m.end()
                continue
            m = _INT_RE.match(text, i)
            if m:
                tokens.append(("number", m.group(0)))
                i = m.end()
                continue
            raise FilterSyntaxError(f"unexpected character {ch!r} in filter expression")
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            word = text[i:j]
            tokens.append(("ident", word))
            i = j
            continue
        raise FilterSyntaxError(f"unexpected character {ch!r} in filter expression")
    tokens.append(("eof", ""))
    return tokens


# ---------------------------------------------------------------------------
# Parser (recursive descent)
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> tuple[str, str]:
        return self._tokens[self._pos]

    def _advance(self) -> tuple[str, str]:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _at_eof(self) -> bool:
        return self._tokens[self._pos][0] == "eof"

    def _expect(self, kind: str, what: str) -> tuple[str, str]:
        tok = self._peek()
        if tok[0] != kind:
            if tok[0] == "eof":
                raise FilterSyntaxError(f"expected {what} but reached end of input")
            raise FilterSyntaxError(f"expected {what} but found {tok[1]!r}")
        return self._advance()

    def _is_keyword(self, word: str) -> bool:
        return word.lower() in (_AND, _OR, _NOT)

    def _is_comparison_op(self, word: str) -> bool:
        return word.lower() in _COMPARISON_OPS

    def parse(self) -> tuple:
        """Parse a complete expression and ensure nothing trails it."""
        node = self._parse_or()
        tok = self._peek()
        if tok[0] != "eof":
            raise FilterSyntaxError(f"unexpected token {tok[1]!r} after expression")
        return node

    def _parse_or(self) -> tuple:
        left = self._parse_and()
        while True:
            tok = self._peek()
            if tok[0] == "ident" and tok[1].lower() == _OR:
                self._advance()
                right = self._parse_and()
                left = ("or", left, right)
            else:
                break
        return left

    def _parse_and(self) -> tuple:
        left = self._parse_not()
        while True:
            tok = self._peek()
            if tok[0] == "ident" and tok[1].lower() == _AND:
                self._advance()
                right = self._parse_not()
                left = ("and", left, right)
            else:
                break
        return left

    def _parse_not(self) -> tuple:
        tok = self._peek()
        if tok[0] == "ident" and tok[1].lower() == _NOT:
            self._advance()
            operand = self._parse_not()
            return ("not", operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> tuple:
        # A comparison is: property op literal, or a parenthesised expression.
        tok = self._peek()
        if tok[0] == "lparen":
            self._advance()
            node = self._parse_or()
            self._expect("rparen", "')'")
            return node
        if tok[0] != "ident":
            if tok[0] == "eof":
                raise FilterSyntaxError("expected a property but reached end of input")
            raise FilterSyntaxError(f"expected a property but found {tok[1]!r}")
        # The property must be an identifier, not a keyword or operator.
        word = tok[1]
        if self._is_keyword(word) or self._is_comparison_op(word):
            raise FilterSyntaxError(f"expected a property but found {word!r}")
        if not _PROPERTY_RE.fullmatch(word):
            raise FilterSyntaxError(f"invalid property name {word!r}")
        self._advance()
        # Now expect a comparison operator.
        op_tok = self._peek()
        if op_tok[0] != "ident" or not self._is_comparison_op(op_tok[1]):
            if op_tok[0] == "eof":
                raise FilterSyntaxError(
                    "expected a comparison operator but reached end of input"
                )
            raise FilterSyntaxError(
                f"expected a comparison operator but found {op_tok[1]!r}"
            )
        op = self._advance()[1].lower()
        # Now expect a literal.
        literal = self._parse_literal()
        return ("cmp", op, word, literal)

    def _parse_literal(self) -> object:
        tok = self._peek()
        kind, value = tok
        if kind == "string":
            self._advance()
            return value
        if kind == "number":
            self._advance()
            if _DECIMAL_RE.fullmatch(value):
                return float(value)
            return int(value)
        if kind == "date":
            self._advance()
            return value
        if kind == "ident":
            lowered = value.lower()
            if lowered == "true":
                self._advance()
                return True
            if lowered == "false":
                self._advance()
                return False
            if lowered == "null":
                self._advance()
                return None
            # A bare identifier where a literal is expected.
            raise FilterSyntaxError(f"expected a literal but found {value!r}")
        if kind == "eof":
            raise FilterSyntaxError("expected a literal but reached end of input")
        raise FilterSyntaxError(f"expected a literal but found {value!r}")


def parse_filter(text: str) -> tuple:
    """Parse a free-form filter expression into a nested-tuple AST.

    Raises :class:`FilterSyntaxError` (a :class:`FilterError`) for anything
    outside the grammar. The message names the offending token text, or
    contains the phrase ``end of input`` when the expression ends early.
    """
    if text is None:
        raise FilterSyntaxError("filter expression is empty")
    tokens = _tokenize(text)
    parser = _Parser(tokens)
    return parser.parse()
