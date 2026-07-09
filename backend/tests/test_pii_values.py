"""Profile-tier PII value detector tests (pure — no DB, no network): validating detectors with
near-miss negatives (Luhn-invalid digit strings, order numbers, out-of-range octets), ratio
math over non-null samples, and the flag floor."""

from app.pii.values import (
    DEFAULT_MATCH_RATIO_FLOOR,
    categories_above_floor,
    value_category_ratios,
)

# ── per-detector positives and near-misses ──────────────────────────────────


def test_email_detection_strict():
    assert value_category_ratios(["bob@example.com"]) == {"contact": 1.0}
    assert value_category_ratios(["not-an-email", "a@b.c", "@example.com"]) == {}


def test_phone_needs_formatting_evidence():
    assert value_category_ratios(["+1 (555) 867-5309"]) == {"contact": 1.0}
    assert value_category_ratios(["555-867-5309"]) == {"contact": 1.0}
    assert value_category_ratios(["(555) 867-5309"]) == {"contact": 1.0}
    assert value_category_ratios(["(555)8675309"]) == {"contact": 1.0}
    # a bare digit run is ambiguous (order id, part number) — abstain
    assert value_category_ratios(["12345678", "99887766"]) == {}


def test_dates_and_zip4_are_not_phones():
    """The high-stakes abstain: every date column samples as digits+separators — flagging
    dates as contact would spam false PII flags across the whole warehouse."""
    assert value_category_ratios(["2024-01-15", "2023-11-02", "2022-06-30"]) == {}
    assert value_category_ratios(["15.03.2024", "01/02/2024"]) == {}
    assert value_category_ratios(["12345-6789"]) == {}  # ZIP+4


def test_card_number_requires_luhn_and_outranks_phone():
    assert value_category_ratios(["4111111111111111"]) == {"financial": 1.0}
    # dashed card: the validating detector claims it — never double-counted as a phone
    assert value_category_ratios(["3782-822463-10005"]) == {"financial": 1.0}
    # same shape, Luhn-invalid: an order number is not a card (16 digits exceed phone range too)
    assert value_category_ratios(["4111111111111112"]) == {}


def test_iban_requires_mod97():
    assert value_category_ratios(["DE89 3704 0044 0532 0130 00"]) == {"financial": 1.0}
    assert value_category_ratios(["DE89370400440532013001"]) == {}  # checksum broken


def test_ssn_formatted_only():
    assert value_category_ratios(["123-45-6789"]) == {"government_id": 1.0}
    # bare 9 digits are ambiguous — abstain entirely
    assert value_category_ratios(["123456789"]) == {}
    # wrong grouping is NEVER an SSN — dashed digits fall back to phone-like contact evidence
    assert value_category_ratios(["123-456-789"]) == {"contact": 1.0}


def test_ip_addresses():
    assert value_category_ratios(["192.168.0.1"]) == {"network_identifier": 1.0}
    assert value_category_ratios(["2001:db8::1"]) == {"network_identifier": 1.0}
    # full uncompressed form and loopback are valid too (exact stdlib validation)
    assert value_category_ratios(
        ["2001:0db8:85a3:0000:0000:8a2e:0370:7334", "::1"]
    ) == {"network_identifier": 1.0}
    # garbage rejected: bad octets, truncated, illegal double-compression, MACs, times
    assert (
        value_category_ratios(
            ["999.1.1.1", "10.0.0", "1::2::3", "00:1A:2B:3C:4D:5E", "12:34:56"]
        )
        == {}
    )


# ── ratio math + the floor ──────────────────────────────────────────────────


def test_ratios_over_non_null_sample():
    values = ["a@b.com", "c@d.org", "e@f.net", None, "", "plain text", 42, "g@h.io"]
    # non-null, non-empty sample = 6; 4 emails -> contact 4/6
    ratios = value_category_ratios(values)
    assert ratios == {"contact": 4 / 6}


def test_floor_gates_stray_matches():
    # one stray email in a mostly-text column never flags it
    values = ["note one", "note two", "note three", "leak@example.com"]
    assert value_category_ratios(values) == {"contact": 0.25}
    assert categories_above_floor(values) == {}
    # a column that is mostly emails flags regardless of its name
    mostly = ["a@b.com", "c@d.com", "e@f.com", "junk"]
    assert categories_above_floor(mostly) == {"contact": 0.75}
    assert DEFAULT_MATCH_RATIO_FLOOR == 0.5
    # the floor is inclusive: exactly 50% flags
    assert categories_above_floor(["a@b.com", "junk"]) == {"contact": 0.5}


def test_fullwidth_digits_never_reach_luhn():
    fullwidth_amex = "３７８２８２２４６３１０００５"
    assert value_category_ratios([fullwidth_amex]) == {}


def test_numeric_values_are_projected():
    assert value_category_ratios([4111111111111111]) == {"financial": 1.0}


def test_empty_and_all_null_yield_no_evidence():
    assert value_category_ratios([]) == {}
    assert value_category_ratios([None, "", "   "]) == {}


def test_deterministic():
    values = ["a@b.com", "192.168.0.1", "4111111111111111", "text"]
    assert value_category_ratios(values) == value_category_ratios(values)
    assert list(value_category_ratios(values)) == [
        "contact",
        "financial",
        "network_identifier",
    ]
