"""Proving test for issue #538: FEED_EXTERNAL_BASE_URL and FEED_TRUST_FORWARDED_HEADERS."""

import app.config as config


def test_issue538_surgical():
    """Both feed settings exist with the required defaults."""
    assert hasattr(
        config, "FEED_EXTERNAL_BASE_URL"
    ), "FEED_EXTERNAL_BASE_URL missing from app.config"
    assert hasattr(
        config, "FEED_TRUST_FORWARDED_HEADERS"
    ), "FEED_TRUST_FORWARDED_HEADERS missing from app.config"
    assert config.FEED_EXTERNAL_BASE_URL == ""
    assert config.FEED_TRUST_FORWARDED_HEADERS is False
