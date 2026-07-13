"""Governance key-hash module (RTBF #76) — exact digests under a fixture pepper.

The digest is pinned two ways: a hardcoded literal (regression pin — any drift in separator,
cap, encoding, or algorithm breaks it) and an independent in-test HMAC computation of the
spec. Plus the 255-cap normalization and the fail-closed missing-pepper error."""

import hashlib
import hmac

import pytest

PEPPER = "fixture-pepper"


def test_exact_known_digest(monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.hashing import subject_key_hash

    # regression pin: hex(HMAC-SHA256(b"fixture-pepper", b"ds-1\x00key-1"))
    assert (
        subject_key_hash("ds-1", "key-1")
        == "e020e4d88b9e2483dcdec30295e28919e96955c1f2548da73b85fd209e23a33f"
    )
    # independent computation of the spec
    expected = hmac.new(PEPPER.encode(), b"ds-1\x00key-1", hashlib.sha256).hexdigest()
    assert subject_key_hash("ds-1", "key-1") == expected


def test_dataset_scoping_changes_the_hash(monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.hashing import subject_key_hash

    assert subject_key_hash("ds-1", "key-1") != subject_key_hash("ds-2", "key-1")


def test_255_cap_matches_mapper_normalization(monkeypatch):
    monkeypatch.setenv("AIDW_SUPPRESSION_PEPPER", PEPPER)
    from app.governance.hashing import subject_key_hash

    long_key = "k" * 300
    assert subject_key_hash("ds", long_key) == subject_key_hash("ds", long_key[:255])
    assert subject_key_hash("ds", long_key) != subject_key_hash("ds", long_key[:254])


def test_missing_pepper_fails_closed_with_a_clear_error(monkeypatch):
    monkeypatch.delenv("AIDW_SUPPRESSION_PEPPER", raising=False)
    from app.governance.hashing import subject_key_hash

    with pytest.raises(RuntimeError, match="AIDW_SUPPRESSION_PEPPER"):
        subject_key_hash("ds", "key")
