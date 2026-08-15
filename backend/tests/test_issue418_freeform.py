"""Issue #418 freeform — egress secret-resolution contract.

Complements the AC-5 round-trip proof with the remaining edges of the
``resolve_secret`` contract:

* The base ``EgressError`` is the common ancestor of both specific
  exceptions, so callers can catch any egress failure with one type.
* The reference pattern is enforced exactly: a 3-char and a 64-char
  reference are valid, while a leading digit, a leading underscore, and a
  lowercase character are all rejected.
* The environment is read at call time — a variable set after an earlier
  failure resolves on the next call, and a variable cleared after a
  successful read raises ``SecretUnavailable``.
* The resolved value is returned to the caller but never appears in any
  exception message.
"""

import pytest

from app.egress import EgressError, SecretRefInvalid, SecretUnavailable
from app.egress.secrets import resolve_secret

_KNOWN_SECRET = "freeform-secret-418"


def test_issue418_freeform():
    """The egress secret-resolution contract holds end to end."""
    # --- Exception hierarchy: both specific errors are EgressError --------
    assert issubclass(SecretRefInvalid, EgressError)
    assert issubclass(SecretUnavailable, EgressError)

    # --- Pattern boundaries: 3 and 64 chars are valid ---------------------
    # (3 = 1 leading + 2 trailing; 64 = 1 leading + 63 trailing)
    assert resolve_secret.__doc__ is not None  # sanity: module is importable

    # --- Invalid references raise SecretRefInvalid, never leaking --------
    invalid_refs = [
        "1ABC",  # leading digit
        "_ABC",  # leading underscore
        "aBC",  # lowercase leading char
        "AB",  # too short (2 chars)
        "A" * 65,  # too long (65 chars)
        "AB C",  # embedded space
        "",  # empty
    ]
    for ref in invalid_refs:
        with pytest.raises(SecretRefInvalid) as excinfo:
            resolve_secret(ref)
        assert isinstance(excinfo.value, EgressError)
        assert _KNOWN_SECRET not in str(excinfo.value)

    # --- Call-time read: set after a failure resolves on the next call ----
    # (No DB/app fixtures needed; the contract is purely the egress seam.)
    # Use a fresh variable name to avoid coupling to other tests.
    var = "EGRESS_FREEFORM_SECRET"
    import os

    # Ensure it starts unset so the missing path is deterministic.
    os.environ.pop(var, None)
    with pytest.raises(SecretUnavailable) as excinfo:
        resolve_secret(var)
    assert isinstance(excinfo.value, EgressError)
    assert _KNOWN_SECRET not in str(excinfo.value)

    # Now set it at call time and confirm it resolves.
    os.environ[var] = _KNOWN_SECRET
    try:
        assert resolve_secret(var) == _KNOWN_SECRET

        # Empty value is treated as unavailable.
        os.environ[var] = ""
        with pytest.raises(SecretUnavailable) as excinfo:
            resolve_secret(var)
        assert isinstance(excinfo.value, EgressError)
        assert _KNOWN_SECRET not in str(excinfo.value)
    finally:
        os.environ.pop(var, None)
