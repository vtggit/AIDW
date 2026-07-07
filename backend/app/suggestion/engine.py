"""Schema-tier dashboard-suggestion rules — pure and deterministic.

Given a dataset's discovered fields (name / native type / is_key / is_nullable / ordinal — the
columns discovery persists) emit candidate dashboard items **from schema alone**, before a single
row is ingested. This is the vision's differentiator: connect an ERP, and useful dashboard items
appear automatically without the user knowing the schema.

Design constraints (validated by a value probe over live Northwind — see docs/BEHAVIORAL-ARCHITECTURE.md §6):

* **Schema-honest.** At this tier there are NO rows, so cardinality / fill-rate / distinct-count do
  not exist. Rules key ONLY on things a schema carries: native type, key flag, nullability, and the
  field *name*. Cardinality-dependent ranking is the *profile-tier* upgrade (after ingest), which
  re-scores these candidates — it is deliberately not attempted here.
* **Noise suppression.** The probe showed name-heuristics fire on high-cardinality fields and make
  junk ("count by CompanyName" = a bar of all 1's; "sum of UnitPrice" = a meaningless total). So:
  SUM only additive-named measures (never price/rate/discount); use as a bar *dimension* only genuine
  low-arity enum-named strings (status/type/category/region/country…), never identifier-ish names
  (name/code/id/city/postalcode…); a time-series needs a real measure (no "count over BirthDate").
* **Low confidence.** Every candidate is ``strategy='schema-only'`` with a modest score — schema-tier
  proposes, profile-tier confirms.

Each candidate carries a ``fingerprint``: a stable hash of its *semantic identity* (item type +
aggregation + role-tagged field names), excluding score/title/tier. Two passes over the same schema
produce identical fingerprints, which is what makes regeneration idempotent and lets the reconciler
tell a still-valid suggestion from one whose schema no longer produces it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# OData/Edm scalar type families (namespace-stripped, so "Edm.Int32" -> "Int32").
_NUMERIC = {"Int16", "Int32", "Int64", "Decimal", "Double", "Single", "Byte", "SByte"}
_TEMPORAL = {"DateTimeOffset", "Date", "DateTime", "Time"}

# Field names are matched by whole TOKEN, not substring, so "AccountId" is never mistaken for a
# "count" measure and "PostalCode" is correctly excluded as a dimension. Names are split across
# camelCase / snake_case / digit boundaries (see _tokens).

# A numeric field is a summable measure when a token reads additive and none reads non-additive.
# Summing a unit price / rate / discount / percentage is meaningless, so those are excluded.
_ADDITIVE_TOKENS = {
    "amount",
    "total",
    "subtotal",
    "qty",
    "quantity",
    "freight",
    "sales",
    "revenue",
    "units",
    "stock",
    "balance",
    "weight",
    "count",
}
_NONADDITIVE_TOKENS = {
    "price",
    "rate",
    "discount",
    "percent",
    "ratio",
    "avg",
    "average",
    "mean",
    "score",
}

# A numeric field whose name ENDS in one of these is an identifier, never a measure (AccountId,
# InvoiceNo, ProductCode) — even if an earlier token happens to look additive.
_IDENTIFIER_SUFFIX_TOKENS = {"id", "code", "number", "no", "guid", "uuid", "key"}

# A string field is usable as a low-arity bar/pie DIMENSION only when a token reads like an enum and
# none reads like a high-cardinality identifier. This is a name-only guess (arity is unknown
# pre-ingestion), so these fire at capped confidence; profile-tier promotes/demotes once rows land.
_GOOD_DIM_TOKENS = {
    "status",
    "type",
    "category",
    "region",
    "country",
    "kind",
    "class",
    "group",
    "priority",
    "level",
    "segment",
    "department",
    "currency",
    "courtesy",
    "gender",
    "method",
    "channel",
    "stage",
    "tier",
}
_DIM_EXCLUDE_TOKENS = {
    "name",
    "code",
    "postal",
    "address",
    "phone",
    "email",
    "title",
    "company",
    "contact",
    "city",
    "url",
    "description",
    "comment",
    "note",
    "id",
    "guid",
    "uuid",
}

_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")


@dataclass(frozen=True)
class SuggestionField:
    """One field bound to a suggestion in a role (measure/dimension/temporal/display)."""

    role: str
    field_name: str


@dataclass(frozen=True)
class SuggestionCandidate:
    """A candidate dashboard item derived from schema alone. Maps 1:1 onto a ``suggestions`` row
    (+ its ``suggestion_fields``); ``fingerprint`` is its per-dataset idempotency key.
    """

    item_type: str  # kpi | bar | line | table (pie reserved for profile-tier)
    aggregation: str  # count | sum | none
    title: str
    rationale: str
    strategy: str  # always "schema-only" at this tier
    score: float
    fields: tuple[SuggestionField, ...]
    fingerprint: str


def _base_type(data_type: str | None) -> str:
    """'Edm.String' -> 'String'; tolerant of a bare type or None."""
    return (data_type or "").split(".")[-1]


def _is_numeric(data_type: str | None) -> bool:
    return _base_type(data_type) in _NUMERIC


def _is_temporal(data_type: str | None) -> bool:
    return _base_type(data_type) in _TEMPORAL


def _is_string(data_type: str | None) -> bool:
    return _base_type(data_type) == "String"


def _tokens(name: str) -> list[str]:
    """Split a field name into lowercase word tokens across camelCase, snake_case and digit
    boundaries. 'AccountId' -> ['account', 'id']; 'UnitsInStock' -> ['units', 'in', 'stock'].
    """
    spaced = _ACRONYM_BOUNDARY.sub(r"\1 \2", _CAMEL_BOUNDARY.sub(r"\1 \2", name or ""))
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]


def _is_additive_measure(name: str) -> bool:
    toks = _tokens(name)
    if not toks or toks[-1] in _IDENTIFIER_SUFFIX_TOKENS:
        return False
    tokset = set(toks)
    if tokset & _NONADDITIVE_TOKENS:
        return False
    return bool(tokset & _ADDITIVE_TOKENS)


def _is_good_dimension(name: str) -> bool:
    tokset = set(_tokens(name))
    if tokset & _DIM_EXCLUDE_TOKENS:
        return False
    return bool(tokset & _GOOD_DIM_TOKENS)


def _fingerprint(
    item_type: str, aggregation: str, fields: list[SuggestionField]
) -> str:
    """Stable hash of a suggestion's *semantic identity* within a dataset. Field bindings are sorted
    so ordering never changes the fingerprint; title/score/strategy are deliberately excluded.
    """
    parts = [item_type, aggregation]
    parts += sorted(f"{sf.role}:{sf.field_name}" for sf in fields)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def generate_suggestions(
    dataset_name: str, fields: list[dict]
) -> list[SuggestionCandidate]:
    """Emit schema-tier candidates for one dataset.

    ``fields`` is a list of dicts with keys ``name``, ``data_type``, ``is_key``, ``is_nullable``,
    ``field_position`` — exactly the shape of a ``discovered_fields`` row. Deterministic: same input
    → same output (including fingerprints).
    """
    out: list[SuggestionCandidate] = []

    def add(item_type, aggregation, title, rationale, sfields, score):
        out.append(
            SuggestionCandidate(
                item_type=item_type,
                aggregation=aggregation,
                title=title,
                rationale=rationale,
                strategy="schema-only",
                score=score,
                fields=tuple(sfields),
                fingerprint=_fingerprint(item_type, aggregation, sfields),
            )
        )

    non_key = [f for f in fields if not f.get("is_key")]
    numerics = [f for f in non_key if _is_numeric(f.get("data_type"))]
    strings = [f for f in non_key if _is_string(f.get("data_type"))]
    temporals = [f for f in fields if _is_temporal(f.get("data_type"))]
    measures = [f for f in numerics if _is_additive_measure(f.get("name", ""))]
    dimensions = [f for f in strings if _is_good_dimension(f.get("name", ""))]

    # R1 row-count KPI — fires on every dataset (generic, hence low score).
    add(
        "kpi",
        "count",
        f"Total {dataset_name}",
        f"Row count of {dataset_name}.",
        [],
        0.40,
    )

    # R2 measure KPI — an additive numeric summed to a headline number.
    for m in measures:
        add(
            "kpi",
            "sum",
            f"Total {m['name']}",
            f"{m['name']} is an additive numeric measure.",
            [SuggestionField("measure", m["name"])],
            0.50,
        )

    # R3 temporal trend — a measure over a date axis (needs BOTH; no bare count-over-time).
    if temporals and measures:
        t, m = temporals[0], measures[0]
        add(
            "line",
            "sum",
            f"{m['name']} over {t['name']}",
            f"Trend of {m['name']} across {t['name']}.",
            [
                SuggestionField("temporal", t["name"]),
                SuggestionField("measure", m["name"]),
            ],
            0.60,
        )

    # R4 count-by-category (semantic) — the dimension had to be interpreted from its name.
    for d in dimensions:
        add(
            "bar",
            "count",
            f"{dataset_name} by {d['name']}",
            f"{d['name']} reads categorical by name (arity confirmed after ingest).",
            [SuggestionField("dimension", d["name"])],
            0.55,
        )

    # R5 measure-by-category (semantic) — an additive measure aggregated across a categorical dim.
    if dimensions and measures:
        d, m = dimensions[0], measures[0]
        add(
            "bar",
            "sum",
            f"{m['name']} by {d['name']}",
            f"{m['name']} aggregated across {d['name']}.",
            [
                SuggestionField("dimension", d["name"]),
                SuggestionField("measure", m["name"]),
            ],
            0.62,
        )

    # R6 detail table — first columns by ordinal; a generic fallback for any non-empty dataset.
    if fields:
        ordered = sorted(
            fields,
            key=lambda f: (
                f["field_position"]
                if f.get("field_position") is not None
                else 1_000_000
            ),
        )
        cols = [f["name"] for f in ordered][:8]
        add(
            "table",
            "none",
            f"{dataset_name} details",
            f"Detail table of the first {len(cols)} fields of {dataset_name}.",
            [SuggestionField("display", c) for c in cols],
            0.35,
        )

    return out
