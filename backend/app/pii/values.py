"""Profile-tier PII value detectors — pure format detection over sampled values (governance #75).

The second tier of the watchdog: where the schema tier reads only field NAMES, this module reads
the sampled VALUES the profiler already holds in memory and reports, per PII category, what
fraction of the non-null sample matches a strict format detector. The reconciler flags a field
only above a match-ratio floor, so one stray email in a comments column never flags it — but a
column that is 80% emails flags regardless of what it is named (the case schema rules can't see).

Detector discipline (the near-miss rules that keep this honest):

* **Validating, not resembling.** Card numbers must pass Luhn AND have a plausible length —
  an order number that happens to be 15 digits but fails Luhn contributes nothing. IBANs must
  pass the real mod-97 check. IPv4 octets must be 0–255.
* **Ambiguity abstains.** A bare digit string could be a phone, an order id, or a part number —
  phones only count with international/formatting evidence (a leading ``+`` or separators).
  Plain dates are NOT date_of_birth evidence (an OrderDate samples identically); DOB stays a
  schema-tier call. Passwords/credentials have no value format at all — never detected here.
* **Pure.** No network, no DB, deterministic; values are str()-projected, None/empty skipped.

Categories emitted here are a SUBSET of the pii_flags CHECK enum: contact (email/phone),
financial (IBAN/card), government_id (formatted SSN), network_identifier (IPv4/IPv6).
"""

from __future__ import annotations

import ipaddress
import re

# a field flags at profile tier only when at least this fraction of its non-null sample matches
DEFAULT_MATCH_RATIO_FLOOR = 0.5

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
# international/formatting evidence required: leading + or internal separators — a bare digit
# run is ambiguous (order ids, part numbers) and abstains. A leading '(' is a separator too
# ('(555) 867-5309').
_PHONE_RE = re.compile(r"^\+?[(0-9][0-9\s\-().]{5,18}[0-9]$")
# date-shaped and ZIP+4-shaped strings are NOT phones ('2024-01-15' has digits and separators
# but samples identically to any OrderDate — the 'ambiguity abstains' contract)
_DATE_SHAPES = (
    re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$"),
    re.compile(r"^\d{1,2}[-./]\d{1,2}[-./]\d{4}$"),
    re.compile(r"^\d{5}-\d{4}$"),
)
_SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Za-z0-9]{11,30}$")
_CARD_STRIP_RE = re.compile(r"[ \-]")


def _is_email(s: str) -> bool:
    return bool(_EMAIL_RE.match(s))


def _is_phone(s: str) -> bool:
    if any(shape.match(s) for shape in _DATE_SHAPES):
        return False
    if not _PHONE_RE.match(s):
        return False
    digits = sum(ch.isdigit() for ch in s)
    if not (7 <= digits <= 15):
        return False
    return s.startswith("+") or bool(re.search(r"[\s\-().]", s))


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_card_number(s: str) -> bool:
    stripped = _CARD_STRIP_RE.sub("", s)
    # isascii: str.isdigit() admits fullwidth digits, whose ord()-48 corrupts the Luhn sum
    return (
        stripped.isascii()
        and stripped.isdigit()
        and 13 <= len(stripped) <= 19
        and _luhn_ok(stripped)
    )


def _is_iban(s: str) -> bool:
    compact = s.replace(" ", "").upper()
    if not _IBAN_RE.match(compact) or not (15 <= len(compact) <= 34):
        return False
    rearranged = compact[4:] + compact[:4]
    number = int("".join(str(int(c, 36)) for c in rearranged))
    return number % 97 == 1


def _is_ssn(s: str) -> bool:
    return bool(_SSN_RE.match(s))


def _is_ip(s: str) -> bool:
    """Exact validation via the stdlib parser: accepts every valid IPv4/IPv6 rendering (full
    form, '::1', ranged octets) and rejects everything else (MACs, times, '1::2::3', 999.x).
    """
    if "." not in s and ":" not in s:
        return False  # ip_address(str) never accepts bare integers, but be explicit
    try:
        ipaddress.ip_address(s)
    except ValueError:
        return False
    return True


def _value_categories(s: str) -> set[str]:
    """Categories one value evidences, with precedence: the VALIDATING detectors (Luhn card,
    mod-97 IBAN, exact SSN grouping, ranged IP octets) claim first; phone — the weakest format,
    'digits with separators' also describes all of the above — only counts when no validating
    detector claimed the value."""
    hits: set[str] = set()
    if _is_email(s):
        hits.add("contact")
    if _is_iban(s) or _is_card_number(s):
        hits.add("financial")
    if _is_ssn(s):
        hits.add("government_id")
    if _is_ip(s):
        hits.add("network_identifier")
    if not hits and _is_phone(s):
        hits.add("contact")
    return hits


def value_category_ratios(values: list) -> dict[str, float]:
    """Per-category match ratio over the non-null str()-projected sample. Categories with a
    zero ratio are omitted; an empty/all-null sample yields {} (no evidence, not evidence of
    absence)."""
    sample = [
        str(v).strip() for v in (values or []) if v is not None and str(v).strip()
    ]
    if not sample:
        return {}
    counts: dict[str, int] = {}
    for s in sample:
        for category in _value_categories(s):
            counts[category] = counts.get(category, 0) + 1
    return {c: n / len(sample) for c, n in sorted(counts.items())}


def categories_above_floor(
    values: list, floor: float = DEFAULT_MATCH_RATIO_FLOOR
) -> dict[str, float]:
    """The reconciler's entry point: only categories whose match ratio clears the floor —
    one stray email in a free-text column never flags it."""
    return {c: r for c, r in value_category_ratios(values).items() if r >= floor}
