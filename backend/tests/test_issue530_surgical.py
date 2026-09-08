"""Proving test for issue #530: EgressDestinationDenied must not leak URL parts."""

import pytest

from app.egress.policy import EgressDestinationDenied, validate_destination


def test_issue530_surgical():
    """The ValueError branch must not include userinfo, query, or fragment."""
    url = "http://user:secret@[::ffff:127.1]/?token=abc#frag"
    with pytest.raises(EgressDestinationDenied) as excinfo:
        validate_destination(url)
    msg = str(excinfo.value)
    # Must not leak userinfo (password)
    assert "secret" not in msg
    # Must not leak query string
    assert "token=abc" not in msg
    # Must not leak fragment
    assert "#frag" not in msg
    # Must name the bracketed host as written or say unparseable
    assert "[::ffff:127.1]" in msg or "unparseable" in msg.lower()
