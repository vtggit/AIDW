"""Issue #500 — egress destination policy (backend/app/egress/policy.py).

Proves the pure, call-time host validation: the every-mode denials, the
strict-mode loopback denials, the EGRESS_ALLOWED_HOSTS exemption, and the
pass-through of RFC1918 / public / ordinary hosts.  Environment variables are
set at call time via monkeypatch so the module's call-time reads are exercised.
"""

import pytest

from app.egress import EgressError
from app.egress.policy import EgressDestinationDenied, validate_destination


def _assert_denied(url: str) -> None:
    with pytest.raises(EgressDestinationDenied):
        validate_destination(url)


def _assert_allowed(url: str) -> None:
    validate_destination(url)


def test_issue500_freeform(monkeypatch):
    # EgressDestinationDenied subclasses the egress EgressError base.
    assert issubclass(EgressDestinationDenied, EgressError)

    # ------------------------------------------------------------------
    # Every-mode denials (EGRESS_POLICY unset / non-strict).
    # ------------------------------------------------------------------
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)

    # Empty or missing host.
    _assert_denied("")
    _assert_denied("https:///path")
    _assert_denied("https://")

    # The literal 0.0.0.0.
    _assert_denied("http://0.0.0.0/")
    _assert_denied("http://0.0.0.0:8080/api")

    # Link-local IPv4 (169.254.0.0/16).
    _assert_denied("http://169.254.0.1/")
    _assert_denied("http://169.254.10.20/")
    _assert_denied("http://169.254.255.255/")

    # Link-local IPv6 (fe80::/10).
    _assert_denied("http://[fe80::1]/")
    _assert_denied("http://[fe80::abcd:1234]/")
    _assert_denied("http://[febf:ffff:ffff:ffff:ffff:ffff:ffff:ffff]/")

    # Loopback targets PASS when EGRESS_POLICY is unset.
    _assert_allowed("http://127.0.0.1/")
    _assert_allowed("http://127.5.6.7/")
    _assert_allowed("http://[::1]/")
    _assert_allowed("http://localhost/")

    # ------------------------------------------------------------------
    # Strict mode: loopback denied, link-local still denied, others pass.
    # ------------------------------------------------------------------
    monkeypatch.setenv("EGRESS_POLICY", "strict")
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)

    _assert_denied("http://127.0.0.1/")
    _assert_denied("http://127.255.255.255/")
    _assert_denied("http://[::1]/")
    _assert_denied("http://localhost/")
    _assert_denied("http://localhost:9000/x")

    # Link-local and 0.0.0.0 remain denied in strict mode too.
    _assert_denied("http://169.254.1.1/")
    _assert_denied("http://[fe80::1]/")
    _assert_denied("http://0.0.0.0/")

    # RFC1918 private addresses pass even in strict mode.
    _assert_allowed("http://10.0.0.5/")
    _assert_allowed("http://172.16.0.1/")
    _assert_allowed("http://172.31.255.255/")
    _assert_allowed("http://192.168.1.100/")

    # Public IP literals and ordinary hostnames pass in strict mode.
    _assert_allowed("http://8.8.8.8/")
    _assert_allowed("http://1.1.1.1/")
    _assert_allowed("http://[2001:4860:4860::8888]/")
    _assert_allowed("https://example.com/")
    _assert_allowed("https://api.vendor.io/v1")

    # A non-strict value does NOT enable loopback denial.
    monkeypatch.setenv("EGRESS_POLICY", "permissive")
    _assert_allowed("http://127.0.0.1/")
    _assert_allowed("http://localhost/")
    _assert_allowed("http://[::1]/")

    # ------------------------------------------------------------------
    # EGRESS_ALLOWED_HOSTS exemption (exact match, whitespace trimmed).
    # ------------------------------------------------------------------
    monkeypatch.setenv("EGRESS_POLICY", "strict")
    monkeypatch.setenv("EGRESS_ALLOWED_HOSTS", "localhost, 127.0.0.1 , 169.254.1.1")

    # Exempted loopback / link-local hosts pass even in strict mode.
    _assert_allowed("http://localhost/")
    _assert_allowed("http://127.0.0.1/")
    _assert_allowed("http://169.254.1.1/")

    # Non-exempt loopback / link-local / 0.0.0.0 still denied.
    _assert_denied("http://127.0.0.2/")
    _assert_denied("http://[::1]/")
    _assert_denied("http://169.254.9.9/")
    _assert_denied("http://0.0.0.0/")

    # Exemption also applies when EGRESS_POLICY is unset (every-mode denials).
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.setenv("EGRESS_ALLOWED_HOSTS", "0.0.0.0, 169.254.0.1")
    _assert_allowed("http://0.0.0.0/")
    _assert_allowed("http://169.254.0.1/")
    _assert_denied("http://169.254.0.2/")

    # ------------------------------------------------------------------
    # Call-time reads: toggling the env between calls changes the outcome.
    # ------------------------------------------------------------------
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    _assert_allowed("http://127.0.0.1/")
    monkeypatch.setenv("EGRESS_POLICY", "strict")
    _assert_denied("http://127.0.0.1/")
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    _assert_allowed("http://127.0.0.1/")
