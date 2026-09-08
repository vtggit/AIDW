"""Proving test for issue #532: distinct failure messages in run_connection_test."""

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.egress.http import EgressAuthError
from app.egress.policy import EgressDestinationDenied
from app.egress.secrets import SecretRefInvalid, SecretUnavailable


def _make_entity():
    return {
        "id": "ct-1",
        "source_id": "src-1",
        "status": "pending",
        "message": None,
        "latency_ms": None,
        "tested_at": None,
    }


def _call_run(exc):
    """Invoke run_connection_test with fetch_bytes raising *exc*; return UPDATE params."""
    entity = _make_entity()

    mock_service = MagicMock()
    mock_service.get_connection_test.return_value = entity

    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"endpoint": "https://erp.example.com/odata"},
        {"metadata_path": "$metadata"},
    ]

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cur)
    cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.api.connection_tests.get_cursor") as mock_gc,
        patch("app.api.connection_tests.egress_http") as mock_egress,
    ):
        mock_gc.return_value = cm
        mock_egress.fetch_bytes.side_effect = exc

        from app.api.connection_tests import run_connection_test

        run_connection_test(
            entity_id="ct-1",
            _user=MagicMock(),
            service=mock_service,
        )

    for call in cur.execute.call_args_list:
        args = call[0]
        if args and "UPDATE connection_tests" in str(args[0]):
            return args[1]
    raise AssertionError("UPDATE statement not found in cursor calls")


def test_issue532_surgical():
    # --- EgressDestinationDenied ---
    params = _call_run(EgressDestinationDenied("denied"))
    assert params[0] == "unreachable"
    assert params[1] == "Destination denied by egress policy."
    assert "erp.example.com" not in params[1]

    # --- SecretUnavailable ---
    params = _call_run(SecretUnavailable("missing"))
    assert params[0] == "unreachable"
    assert params[1] == "Credential unavailable for this source."
    assert "erp.example.com" not in params[1]

    # --- SecretRefInvalid ---
    params = _call_run(SecretRefInvalid("bad-ref"))
    assert params[0] == "unreachable"
    assert params[1] == "Credential unavailable for this source."
    assert "erp.example.com" not in params[1]

    # --- EgressAuthError (existing behaviour preserved) ---
    params = _call_run(EgressAuthError("401"))
    assert params[0] == "auth_failed"
    assert params[1] == "Authentication failed against the source endpoint."
    assert "erp.example.com" not in params[1]

    # --- urllib.error.URLError ---
    params = _call_run(urllib.error.URLError("connection refused"))
    assert params[0] == "unreachable"
    assert params[1] == "Source endpoint is unreachable."
    assert "erp.example.com" not in params[1]

    # --- TimeoutError (socket timeout) ---
    params = _call_run(TimeoutError("timed out"))
    assert params[0] == "unreachable"
    assert params[1] == "Source endpoint is unreachable."
    assert "erp.example.com" not in params[1]

    # --- Non-egress/network exception must propagate ---
    entity = _make_entity()
    mock_service = MagicMock()
    mock_service.get_connection_test.return_value = entity

    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"endpoint": "https://erp.example.com/odata"},
        {"metadata_path": "$metadata"},
    ]
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cur)
    cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.api.connection_tests.get_cursor") as mock_gc,
        patch("app.api.connection_tests.egress_http") as mock_egress,
    ):
        mock_gc.return_value = cm
        mock_egress.fetch_bytes.side_effect = RuntimeError("boom")

        from app.api.connection_tests import run_connection_test

        with pytest.raises(RuntimeError, match="boom"):
            run_connection_test(
                entity_id="ct-1",
                _user=MagicMock(),
                service=mock_service,
            )
