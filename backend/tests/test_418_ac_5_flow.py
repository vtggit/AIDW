"""Issue #418 AC-5 — egress secret resolution round-trips.

Proves the egress secret-resolution contract:

* A well-formed secret reference resolves to the content of the named
  environment variable (read at call time).
* An invalid reference (lowercase, too short, too long) raises
  ``SecretRefInvalid`` and the exception message never contains the secret.
* A missing (or empty) variable raises ``SecretUnavailable`` and the
  exception message never contains the secret.

The module reads the environment at call time, so each test sets the
variable first via ``monkeypatch.setenv`` (and the missing-variable path via
``monkeypatch.delenv``).  No DB or app fixtures are required — the contract
is purely about the egress secret seam.
"""

import pytest

from app.egress import EgressError, SecretRefInvalid, SecretUnavailable
from app.egress.secrets import resolve_secret

# A known, non-trivial secret value used to prove no leakage into messages.
_KNOWN_SECRET = "s3cr3t-value-418"


def test_418_ac_5_round_trips(monkeypatch):
    """A well-formed reference round-trips to the env var's content."""
    monkeypatch.setenv("EGRESS_TEST_SECRET", _KNOWN_SECRET)
    assert resolve_secret("EGRESS_TEST_SECRET") == _KNOWN_SECRET


def test_418_ac_5_invalid_ref_raises_and_does_not_leak(monkeypatch):
    """Invalid references raise SecretRefInvalid without leaking the secret."""
    # The variable is set so that, if the code path were wrong, the value
    # would be available to leak — proving the message stays clean.
    monkeypatch.setenv("EGRESS_TEST_SECRET", _KNOWN_SECRET)

    invalid_refs = [
        "lowercase",  # lowercase
        "AB",  # too short (2 chars)
        "A" * 65,  # too long (65 chars)
    ]
    for ref in invalid_refs:
        with pytest.raises(SecretRefInvalid) as excinfo:
            resolve_secret(ref)
        assert isinstance(excinfo.value, EgressError)
        assert _KNOWN_SECRET not in str(excinfo.value)


def test_418_ac_5_missing_var_raises_and_does_not_leak(monkeypatch):
    """A missing variable raises SecretUnavailable without leaking the secret."""
    monkeypatch.delenv("EGRESS_TEST_SECRET", raising=False)
    with pytest.raises(SecretUnavailable) as excinfo:
        resolve_secret("EGRESS_TEST_SECRET")
    assert isinstance(excinfo.value, EgressError)
    assert _KNOWN_SECRET not in str(excinfo.value)


def test_418_ac_5_empty_var_raises_and_does_not_leak(monkeypatch):
    """An empty variable raises SecretUnavailable without leaking the secret."""
    monkeypatch.setenv("EGRESS_TEST_SECRET", "")
    with pytest.raises(SecretUnavailable) as excinfo:
        resolve_secret("EGRESS_TEST_SECRET")
    assert isinstance(excinfo.value, EgressError)
    assert _KNOWN_SECRET not in str(excinfo.value)
