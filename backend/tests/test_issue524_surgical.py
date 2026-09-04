"""Proving test for issue #524 — non-canonical IP-like hosts and :: denial."""

import pytest

from app.egress.policy import EgressDestinationDenied, validate_destination


def test_issue524_surgical(monkeypatch):
    # Ensure clean state
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)

    # --- Non-canonical IP-like hosts denied in ALL modes ---
    denied_hosts = [
        "127.1",
        "127.0.1",
        "2130706433",
        "0x7f000001",
        "0x7f.1",
        "0177.0.0.1",
        "017700000001",
        "127.000.000.001",
        "0",
        "0x0",
        "0.0",
        "2852039166",
    ]
    for mode in (None, "strict"):
        if mode is None:
            monkeypatch.delenv("EGRESS_POLICY", raising=False)
        else:
            monkeypatch.setenv("EGRESS_POLICY", mode)
        for h in denied_hosts:
            with pytest.raises(EgressDestinationDenied):
                validate_destination(f"http://{h}/")

    # --- IPv6 unspecified address denied in ALL modes ---
    for mode in (None, "strict"):
        if mode is None:
            monkeypatch.delenv("EGRESS_POLICY", raising=False)
        else:
            monkeypatch.setenv("EGRESS_POLICY", mode)
        with pytest.raises(EgressDestinationDenied):
            validate_destination("http://[::]/")

    # --- Allowed destinations under strict ---
    monkeypatch.setenv("EGRESS_POLICY", "strict")
    for url in [
        "http://example.com/",
        "http://localhost.example.com/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://8.8.8.8/",
        "http://[2001:db8::1]/",
        "http://[::ffff:8.8.8.8]/",
    ]:
        validate_destination(url)

    # --- Allowed destinations with EGRESS_POLICY unset ---
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    for url in [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
    ]:
        validate_destination(url)
