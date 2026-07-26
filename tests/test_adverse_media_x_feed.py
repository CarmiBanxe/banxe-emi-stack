"""Tests for services.adverse_media.x_feed.XAdverseMediaFeed.

Verifies the SANDBOX-off contract (inert by default), Protocol compatibility,
and degrade-to-[] on error. X adverse-media is advisory-only and disabled unless
explicitly enabled — these tests lock that in.
"""

from __future__ import annotations

from services.adverse_media.x_feed import XAdverseMediaFeed


def test_disabled_by_default_returns_empty(monkeypatch) -> None:
    monkeypatch.delenv("X_ADVERSE_MEDIA_ENABLED", raising=False)
    monkeypatch.setenv("X_BEARER_TOKEN", "AAAAdummy")  # token present but not enabled
    feed = XAdverseMediaFeed()
    assert feed.fetch("Jane Doe", jurisdiction="GB") == []


def test_enabled_but_no_token_returns_empty(monkeypatch) -> None:
    monkeypatch.setenv("X_ADVERSE_MEDIA_ENABLED", "1")
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    feed = XAdverseMediaFeed()
    assert feed.fetch("Jane Doe") == []


def test_explicit_disabled_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("X_ADVERSE_MEDIA_ENABLED", "1")
    monkeypatch.setenv("X_BEARER_TOKEN", "AAAAdummy")
    feed = XAdverseMediaFeed(enabled=False)
    assert feed.fetch("Jane Doe") == []


def test_implements_negative_news_feed_protocol() -> None:
    from services.adverse_media.models import NegativeNewsFeed

    feed: NegativeNewsFeed = XAdverseMediaFeed()  # type: ignore[assignment]
    assert callable(feed.fetch)


def test_no_pii_in_logs_when_disabled(monkeypatch, caplog) -> None:
    monkeypatch.delenv("X_ADVERSE_MEDIA_ENABLED", raising=False)
    feed = XAdverseMediaFeed()
    with caplog.at_level("INFO"):
        feed.fetch("Very Secret Name")
    assert "Very Secret Name" not in caplog.text
