"""Proving test for issue #526 — surgical egress policy fixes."""

import pytest

from app.egress.policy import EgressDestinationDenied, validate_destination


@pytest.fixture(autouse=True)
def _clean_egress_env(monkeypatch):
    """Ensure EGRESS_POLICY and EGRESS_ALLOWED_HOSTS are unset by default."""
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)


def test_issue526_surgical(monkeypatch):
    # --- 1. Bracketed hosts that urlsplit rejects raise EgressDestinationDenied ---
    for url in (
        "http://[::ffff:127.1]/",
        "http://[0x7f000001]/",
        "http://[localhost]/",
        "http://[127.0.0.1]/",
    ):
        for policy in ("strict", None):
            if policy is None:
                monkeypatch.delenv("EGRESS_POLICY", raising=False)
            else:
                monkeypatch.setenv("EGRESS_POLICY", policy)
            with pytest.raises(EgressDestinationDenied):
                validate_destination(url)

    # --- 2. Case-insensitive EGRESS_ALLOWED_HOSTS ---
    monkeypatch.setenv("EGRESS_POLICY", "strict")
    monkeypatch.setenv("EGRESS_ALLOWED_HOSTS", "localhost")
    for url in ("http://localhost/", "http://LOCALHOST/", "http://LocalHost/"):
        validate_destination(url)

    monkeypatch.setenv("EGRESS_ALLOWED_HOSTS", "LOCALHOST")
    for url in ("http://localhost/", "http://LOCALHOST/", "http://LocalHost/"):
        validate_destination(url)

    # --- 3. Existing behaviour preserved ---
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    validate_destination("http://example.com/")
    validate_destination("http://[2001:db8::1]/")
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://localhost/")
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://[::ffff:127.0.0.1]/")

    # --- 4. IPv6 unspecified in every spelling, every mode ---
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    for url in (
        "http://[::0]/",
        "http://[0:0:0:0:0:0:0:0]/",
        "http://[0000::0000]/",
    ):
        with pytest.raises(EgressDestinationDenied):
            validate_destination(url)

    monkeypatch.setenv("EGRESS_POLICY", "strict")
    for url in (
        "http://[::0]/",
        "http://[0:0:0:0:0:0:0:0]/",
        "http://[0000::0000]/",
    ):
        with pytest.raises(EgressDestinationDenied):
            validate_destination(url)
