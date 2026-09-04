"""Proving test for issue #518: case-insensitive localhost and IPv4-mapped IPv6."""

import pytest

from app.egress.policy import EgressDestinationDenied, validate_destination


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure EGRESS_POLICY and EGRESS_ALLOWED_HOSTS are unset."""
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)


def test_issue518_surgical(monkeypatch):
    # --- Case-insensitive localhost under strict ---
    monkeypatch.setenv("EGRESS_POLICY", "strict")

    for url in (
        "http://LOCALHOST:8010/",
        "http://LocalHost/",
        "http://localhost/",
    ):
        with pytest.raises(EgressDestinationDenied):
            validate_destination(url)

    # --- IPv4-mapped IPv6 loopback under strict ---
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://[::ffff:127.0.0.1]/")

    # --- IPv4-mapped IPv6 link-local (denied in all modes) ---
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://[::ffff:169.254.1.1]/")

    # --- IPv4-mapped IPv6 0.0.0.0 (denied in all modes) ---
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://[::ffff:0.0.0.0]/")

    # --- Allowed destinations remain allowed under strict ---
    validate_destination("http://example.com/")
    validate_destination("http://10.0.0.1/")
    validate_destination("http://192.168.1.1/")
    validate_destination("http://[2001:db8::1]/")

    # --- Non-strict mode: loopback is allowed ---
    monkeypatch.setenv("EGRESS_POLICY", "permissive")
    validate_destination("http://localhost/")
    validate_destination("http://127.0.0.1/")
    validate_destination("http://[::1]/")
    validate_destination("http://[::ffff:127.0.0.1]/")

    # --- Non-strict mode: link-local still denied ---
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://169.254.1.1/")
    with pytest.raises(EgressDestinationDenied):
        validate_destination("http://[::ffff:169.254.1.1]/")
