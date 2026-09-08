"""Proving test for issue #531: _fetch_metadata exception mapping."""

from unittest.mock import patch

import pytest

from app.discovery.service import DiscoveryError, _fetch_metadata
from app.egress.http import (
    EgressAuthError,
    EgressError,
    SecretRefInvalidAuthError,
    SecretUnavailableAuthError,
)
from app.egress.policy import EgressDestinationDenied

URL = "https://erp.example.com/odata/$metadata"


def test_issue531_surgical():
    # SecretUnavailableAuthError → "credential unavailable for this source"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=SecretUnavailableAuthError("secret not found"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "credential unavailable for this source"
        assert isinstance(ei.value.__cause__, SecretUnavailableAuthError)
        assert "erp.example.com" not in str(ei.value)
        assert URL not in str(ei.value)

    # SecretRefInvalidAuthError → "credential unavailable for this source"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=SecretRefInvalidAuthError("bad ref"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "credential unavailable for this source"
        assert isinstance(ei.value.__cause__, SecretRefInvalidAuthError)

    # Other EgressAuthError → "authentication against the source failed"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=EgressAuthError("401 unauthorized"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "authentication against the source failed"
        assert isinstance(ei.value.__cause__, EgressAuthError)
        assert "erp.example.com" not in str(ei.value)

    # EgressDestinationDenied → "destination denied by egress policy"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=EgressDestinationDenied("blocked"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "destination denied by egress policy"
        assert isinstance(ei.value.__cause__, EgressDestinationDenied)
        assert "erp.example.com" not in str(ei.value)

    # EgressError (base) → "source endpoint unreachable"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=EgressError("500 internal"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "source endpoint unreachable"
        assert isinstance(ei.value.__cause__, EgressError)

    # TimeoutError → "source endpoint unreachable"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=TimeoutError("timed out"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "source endpoint unreachable"
        assert isinstance(ei.value.__cause__, TimeoutError)

    # ConnectionError → "source endpoint unreachable"
    with patch(
        "app.discovery.service.fetch_bytes",
        side_effect=ConnectionError("refused"),
    ):
        with pytest.raises(DiscoveryError) as ei:
            _fetch_metadata(URL)
        assert str(ei.value) == "source endpoint unreachable"
        assert isinstance(ei.value.__cause__, ConnectionError)

    # RuntimeError propagates unchanged (no blanket except)
    with (
        patch(
            "app.discovery.service.fetch_bytes",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        _fetch_metadata(URL)
