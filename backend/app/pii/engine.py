"""Schema-tier PII detection rules — pure and deterministic (governance #75).

Given a dataset's discovered fields (name / data_type / is_key), emit candidate PII flags from
schema alone — before a single row is sampled. Mirrors the suggestion engine's discipline
(doc §10): field names match by whole TOKEN across camelCase / snake_case / digit boundaries,
never by substring — so ``EmailAddress`` is a contact candidate but ``EmailedCount`` is not.

Design constraints (from the adversarially-verified pillar design, issue #75):

* **Deterministic, reproducible, auditable.** No NER, no LLM, no thresholds tuned at runtime:
  the same input always yields the same candidates INCLUDING fingerprints. An LLM tier is a
  later opt-in worker-side layer.
* **Schema-honest.** At this tier there are no values; rules key only on the field name tokens
  and the key flag. Format detection over sampled values (email/IBAN/Luhn/...) is the
  profile-tier module's job — it upgrades these candidates, it does not replace them.
* **Key fields are always candidates.** ``is_key`` fields become ``direct_identifier``
  candidates at elevated confidence regardless of name: business keys are stored VERBATIM in
  the op-log (``ingested_records.business_key``), so a key that identifies a person (email,
  customer number) is exactly the exposure the watchdog exists to surface. A key named like a
  stronger category keeps that category with the elevated confidence.
* **Fail toward review, not silence.** A false positive costs a steward one dismiss (sticky);
  a false negative leaks PII at rest — so category token lists err on the inclusive side and
  the reconciler's human overrides do the narrowing.

Each candidate carries ``fingerprint = sha256("<field name>|<category>")`` — the semantic
identity the reconciler upserts on (confidence/tier/rationale deliberately excluded), so a
profile-tier confirmation upgrades the same flag instead of duplicating it.
"""

from __future__ import annotations

import hashlib
import re

DETECTION_TIER_SCHEMA = "schema"

# Confidence ladder: name-rule match < key field < name-rule match ON a key field.
_CONFIDENCE_NAME_RULE = 0.6
_CONFIDENCE_KEY_FIELD = 0.75
_CONFIDENCE_NAME_RULE_ON_KEY = 0.8

_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")


def _tokens(name: str) -> list[str]:
    """Split a field name into lowercase word tokens across camelCase, snake_case and digit
    boundaries — the suggestion engine's splitter discipline. 'EmailAddress' ->
    ['email', 'address']; 'EmailedCount' -> ['emailed', 'count']."""
    spaced = _ACRONYM_BOUNDARY.sub(r"\1 \2", _CAMEL_BOUNDARY.sub(r"\1 \2", name or ""))
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]


# ── the rule table ──────────────────────────────────────────────────────────
# SINGLE tokens: any one present flags the category. PAIRS: both present flags it (order-free —
# 'BirthDate' and 'DateOfBirth' both carry {birth, date}). Whole tokens only, so 'emailed',
# 'shipped', 'accountable' never fire.

_SINGLE_TOKENS: dict[str, frozenset[str]] = {
    "contact": frozenset({"email", "phone", "mobile", "fax", "telephone"}),
    "government_id": frozenset({"ssn", "passport", "nino"}),
    "financial": frozenset({"iban", "swift", "bic", "salary"}),
    "health": frozenset({"diagnosis", "medical", "allergy", "disability"}),
    "date_of_birth": frozenset({"dob", "birthdate", "birthday"}),
    "location": frozenset({"address", "street", "zip", "latitude", "longitude", "geo"}),
    "credential": frozenset({"password", "secret", "pin", "credential"}),
    "network_identifier": frozenset({"ip", "mac", "hostname", "imei"}),
    "direct_identifier": frozenset(
        {"surname", "forename", "nickname", "initials", "username", "login"}
    ),
}

_PAIR_TOKENS: dict[str, tuple[frozenset[str], ...]] = {
    "government_id": (
        frozenset({"tax", "id"}),
        frozenset({"national", "id"}),
        frozenset({"social", "security"}),
    ),
    "financial": (
        frozenset({"credit", "card"}),
        frozenset({"card", "number"}),
        frozenset({"bank", "account"}),
    ),
    "health": (frozenset({"blood", "type"}),),
    "date_of_birth": (frozenset({"birth", "date"}),),
    "location": (
        frozenset({"postal", "code"}),
        frozenset({"zip", "code"}),
        frozenset({"home", "city"}),
    ),
    "credential": (
        frozenset({"api", "key"}),
        frozenset({"access", "token"}),
    ),
    "network_identifier": (frozenset({"user", "agent"}),),
    "direct_identifier": (
        frozenset({"first", "name"}),
        frozenset({"last", "name"}),
        frozenset({"middle", "name"}),
        frozenset({"full", "name"}),
        frozenset({"given", "name"}),
        frozenset({"family", "name"}),
        frozenset({"maiden", "name"}),
        frozenset({"user", "name"}),
    ),
}

# Deterministic emission order for categories on the same field.
_CATEGORY_ORDER = (
    "direct_identifier",
    "contact",
    "government_id",
    "financial",
    "health",
    "date_of_birth",
    "location",
    "credential",
    "network_identifier",
    "other",
)


def pii_fingerprint(field_name: str, category: str) -> str:
    """sha256('<field name>|<category>') — the reconciler's upsert identity. Public so the
    profile tier computes the SAME fingerprint a schema-tier detection did, and therefore
    UPGRADES that flag rather than duplicating it."""
    return hashlib.sha256(f"{field_name}|{category}".encode()).hexdigest()


# internal alias kept for the existing call sites in this module
_fingerprint = pii_fingerprint


def _name_rule_categories(tokens: list[str]) -> dict[str, str]:
    """{category: matched-rule description} for every category the token set fires."""
    tokset = set(tokens)
    hits: dict[str, str] = {}
    matched_singles: dict[str, set[str]] = {}
    for category, singles in _SINGLE_TOKENS.items():
        matched = set(tokset & singles)
        if matched:
            matched_singles[category] = matched
            preferred = sorted(matched - {"address"}) or sorted(matched)
            hits[category] = f"name token '{preferred[0]}'"
    for category, pairs in _PAIR_TOKENS.items():
        if category in hits:
            continue
        for pair in pairs:
            if pair <= tokset:
                joined = "+".join(f"'{t}'" for t in sorted(pair))
                hits[category] = f"name tokens {joined}"
                break
    # the generic 'address' token yields to a more specific category on the same name
    # ('EmailAddress' is contact, 'IPAddress' is a network identifier) — but ONLY when it is
    # the sole location evidence; an independent signal ('zip', 'geo', a postal-code pair)
    # keeps the location flag (fail toward review — never silence real evidence)
    if matched_singles.get("location") == {"address"} and (
        {"contact", "network_identifier"} & hits.keys()
    ):
        surviving_pair = next(
            (p for p in _PAIR_TOKENS["location"] if p <= (tokset - {"address"})), None
        )
        if surviving_pair is None:
            del hits["location"]
        else:
            joined = "+".join(f"'{t}'" for t in sorted(surviving_pair))
            hits["location"] = f"name tokens {joined}"
    return hits


def detect_pii_candidates(fields: list[dict]) -> list[dict]:
    """The pure schema-tier pass: candidate PII flags for a list of discovered-field dicts
    (``name``, ``data_type``, ``is_key``). Deterministic: input order and the fixed category
    order fully determine output order; fingerprints are stable across runs. One candidate per
    (field, category) — a key field that also matches a name rule keeps the stronger category
    at the elevated key confidence instead of emitting a duplicate direct_identifier."""
    candidates: list[dict] = []
    for f in fields or []:
        field_name = str(f.get("name") or "")
        if not field_name:
            continue
        is_key = bool(f.get("is_key"))
        hits = _name_rule_categories(_tokens(field_name))

        if is_key and not hits:
            # business keys are stored verbatim in the op-log — always surface key fields;
            # a key that matched ANY name rule keeps that (stronger) category below, boosted,
            # instead of gaining a generic direct_identifier duplicate
            candidates.append(
                {
                    "field_name": field_name,
                    "category": "direct_identifier",
                    "confidence": _CONFIDENCE_KEY_FIELD,
                    "rationale": "key field — business keys are stored verbatim in the op-log",
                    "detection_tier": DETECTION_TIER_SCHEMA,
                    "fingerprint": _fingerprint(field_name, "direct_identifier"),
                }
            )

        for category in _CATEGORY_ORDER:
            rule = hits.get(category)
            if rule is None:
                continue
            confidence = (
                _CONFIDENCE_NAME_RULE_ON_KEY if is_key else _CONFIDENCE_NAME_RULE
            )
            rationale = rule + (" on a key field" if is_key else "")
            candidates.append(
                {
                    "field_name": field_name,
                    "category": category,
                    "confidence": confidence,
                    "rationale": rationale,
                    "detection_tier": DETECTION_TIER_SCHEMA,
                    "fingerprint": _fingerprint(field_name, category),
                }
            )
    return candidates
