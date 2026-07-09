"""Schema-tier PII detector tests (pure — no DB, no network): named positive AND negative
cases per the AC (issue #89), whole-token discipline, key-field elevation, fingerprint
stability, and determinism."""

import hashlib

from app.pii.engine import _tokens, detect_pii_candidates


def _one(fields):
    out = detect_pii_candidates(fields)
    assert len(out) == 1, out
    return out[0]


def _categories(name, **kw):
    return [c["category"] for c in detect_pii_candidates([{"name": name, **kw}])]


# ── the AC's named cases ────────────────────────────────────────────────────


def test_email_address_flags_contact_with_fingerprint():
    c = _one([{"name": "EmailAddress", "data_type": "Edm.String"}])
    assert c["category"] == "contact"
    assert c["detection_tier"] == "schema"
    assert 0 < c["confidence"] < 1
    assert "email" in c["rationale"]
    expected = hashlib.sha256(b"EmailAddress|contact").hexdigest()
    assert c["fingerprint"] == expected


def test_emailed_count_is_not_contact():
    """Whole-token matching, never substring: 'Emailed' is not 'email'."""
    assert (
        detect_pii_candidates([{"name": "EmailedCount", "data_type": "Edm.Int32"}])
        == []
    )


def test_key_field_yields_direct_identifier_elevated():
    c = _one([{"name": "CustomerID", "data_type": "Edm.String", "is_key": True}])
    assert c["category"] == "direct_identifier"
    assert c["confidence"] > 0.6  # elevated above the plain name-rule confidence
    assert "op-log" in c["rationale"]


# ── category coverage (positive + near-miss negative per family) ────────────


def test_category_rules_positive_and_negative():
    assert _categories("Phone_Number") == ["contact"]
    assert _categories("BirthDate") == ["date_of_birth"]
    assert _categories("DateOfBirth") == ["date_of_birth"]
    assert _categories("PostalCode") == ["location"]
    assert _categories("ApiKey") == ["credential"]
    assert _categories("TaxId") == ["government_id"]
    assert _categories("CreditCardNumber") == ["financial"]
    assert _categories("BloodType") == ["health"]
    assert _categories("UserAgent") == ["network_identifier"]
    assert _categories("FirstName") == ["direct_identifier"]
    # near-misses: single half of a pair, or an unrelated token, never fires
    assert _categories("CardHolderGreeting") == []
    assert _categories("Birthplace") == []  # 'birth' alone is not date_of_birth
    assert _categories("ShipCountry") == []
    assert _categories("UnitPrice") == []
    assert _categories("Description") == []


def test_key_field_with_stronger_category_keeps_it_boosted_no_duplicate():
    """A key named like a stronger category keeps that category at key confidence — exactly
    one candidate, not a direct_identifier duplicate."""
    c = _one([{"name": "Email", "data_type": "Edm.String", "is_key": True}])
    assert c["category"] == "contact"
    assert c["confidence"] == 0.8
    assert "on a key field" in c["rationale"]


def test_key_field_named_like_person_no_duplicate():
    c = _one([{"name": "username", "data_type": "Edm.String", "is_key": True}])
    assert c["category"] == "direct_identifier"
    assert c["confidence"] == 0.8


def test_multi_category_fields_fixed_order_and_no_silencing():
    """Per-field emission follows _CATEGORY_ORDER, and the 'address' demotion never silences
    INDEPENDENT location evidence (zip/geo/postal-code) on the same name."""
    assert _categories("ssn_email") == ["contact", "government_id"]
    assert _categories("EmailAddressZip") == ["contact", "location"]
    assert _categories("EmailAddressPostalCode") == ["contact", "location"]
    assert _categories("ip_geo_address") == ["location", "network_identifier"]
    # the intended demotions still hold when 'address' is the sole location evidence
    assert _categories("EmailAddress") == ["contact"]
    assert _categories("IPAddress") == ["network_identifier"]
    assert _categories("HomeAddress") == ["location"]  # no specific category — kept


# ── determinism + robustness ────────────────────────────────────────────────


def test_deterministic_including_fingerprints_and_order():
    fields = [
        {"name": "OrderID", "data_type": "Edm.Int32", "is_key": True},
        {"name": "Email", "data_type": "Edm.String"},
        {"name": "home_city", "data_type": "Edm.String"},
        {"name": "Freight", "data_type": "Edm.Decimal"},
    ]
    a = detect_pii_candidates(fields)
    b = detect_pii_candidates(fields)
    assert a == b
    assert [c["field_name"] for c in a] == ["OrderID", "Email", "home_city"]


def test_tokens_split_camel_snake_acronym():
    assert _tokens("EmailAddress") == ["email", "address"]
    assert _tokens("date_of_birth") == ["date", "of", "birth"]
    assert _tokens("IPAddress") == ["ip", "address"]
    assert _tokens("") == []


def test_empty_and_nameless_fields_are_skipped():
    assert detect_pii_candidates([]) == []
    assert detect_pii_candidates([{"data_type": "Edm.String"}, {"name": ""}]) == []
