"""Proving test for issue #502: fetch_bytes validates egress destination."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.egress.http import fetch_bytes
from app.egress.policy import EgressDestinationDenied


def test_issue502_surgical(monkeypatch):
    """fetch_bytes must reject link-local destinations before any connection."""
    # Ensure EGRESS_POLICY is unset (default mode) and no hosts are exempted.
    monkeypatch.delenv("EGRESS_POLICY", raising=False)
    monkeypatch.delenv("EGRESS_ALLOWED_HOSTS", raising=False)

    # 169.254.169.254 is link-local — denied in every mode.
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(EgressDestinationDenied):
            fetch_bytes("http://169.254.169.254/latest/meta-data/")
        # No HTTP request must have been attempted.
        mock_urlopen.assert_not_called()
