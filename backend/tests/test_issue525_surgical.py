"""Proving test for issue #525 — loopback hostname spellings under strict egress."""

import pytest

from app.egress.policy import EgressDestinationDenied, validate_destination


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure EGRESS_POLICY and EGRESS_ALLOWED_HOSTS are unset."""
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)


def test_issue525_surgical(monkeypatch):
    """All loopback hostname spellings are denied under strict; allowed hosts pass."""
    monkeypatch.setenv("EGRESS_POLICY", "strict")

    # Every spelling of the loopback name must be denied.
    denied_urls = [
        "http://localhost/",
        "http://localhost./",
        "http://LOCALHOST./",
        "http://foo.localhost/",
        "http://a.b.localhost/",
        "http://FOO.LocalHost/",
        "http://localhost.localdomain/",
    ]
    for url in denied_urls:
        with pytest.raises(EgressDestinationDenied):
            validate_destination(url)

    # Destinations that must remain allowed under strict.
    allowed_urls = [
        "http://localhost.example.com/",
        "http://example.com/",
        "http://mylocalhost.example.com/",
        "http://10.0.0.1/",
    ]
    for url in allowed_urls:
        validate_destination(url)  # must not raise

    # Without strict mode, loopback hostnames pass.
    monkeypatch.delenv("EGRESS_POLICY")
    validate_destination("http://localhost/")
    validate_destination("http://localhost./")
