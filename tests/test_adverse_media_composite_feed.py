"""Tests for services.adverse_media.composite_feed.CompositeFeed.

Locks in: aggregation across sub-feeds, de-duplication by article_id and by
(source, url) fallback, isolation of a failing sub-feed (degrade-to-[] per
node), Protocol compatibility, and SANDBOX posture (all-disabled sub-feeds
compose to []).
"""

from __future__ import annotations

from services.adverse_media.composite_feed import CompositeFeed
from services.adverse_media.models import AdverseMediaArticle, NegativeNewsFeed
from services.adverse_media.rss_feed import RssAdverseMediaFeed
from services.adverse_media.web_feed import WebSearchAdverseMediaFeed
from services.adverse_media.x_feed import XAdverseMediaFeed


def _article(article_id: str, source: str = "stub", url: str | None = None) -> AdverseMediaArticle:
    return AdverseMediaArticle(
        article_id=article_id,
        subject_name="Jane Doe",
        headline=f"headline {article_id}",
        source=source,
        categories=["test"],
        url=url,
    )


class _StubFeed:
    def __init__(self, articles: list[AdverseMediaArticle]) -> None:
        self._articles = articles

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        return list(self._articles)


class _BoomFeed:
    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        raise RuntimeError("sub-feed exploded")


def test_implements_negative_news_feed_protocol() -> None:
    feed: NegativeNewsFeed = CompositeFeed([])
    assert callable(feed.fetch)


def test_empty_feed_list_returns_empty() -> None:
    assert CompositeFeed([]).fetch("Jane Doe") == []


def test_aggregates_across_sub_feeds() -> None:
    composite = CompositeFeed(
        [_StubFeed([_article("a-1")]), _StubFeed([_article("a-2"), _article("a-3")])]
    )
    articles = composite.fetch("Jane Doe", jurisdiction="GB")
    assert [a.article_id for a in articles] == ["a-1", "a-2", "a-3"]


def test_deduplicates_by_article_id() -> None:
    dup = _article("a-1")
    composite = CompositeFeed([_StubFeed([dup]), _StubFeed([dup, _article("a-2")])])
    articles = composite.fetch("Jane Doe")
    assert [a.article_id for a in articles] == ["a-1", "a-2"]


def test_deduplicates_by_source_url_fallback() -> None:
    # different article_ids, same (source, url) → second one dropped
    first = _article("a-1", source="rss:news", url="https://news.example.com/a/1")
    second = _article("a-9", source="rss:news", url="https://news.example.com/a/1")
    composite = CompositeFeed([_StubFeed([first]), _StubFeed([second])])
    articles = composite.fetch("Jane Doe")
    assert [a.article_id for a in articles] == ["a-1"]


def test_same_url_from_different_sources_is_kept() -> None:
    first = _article("a-1", source="rss:news", url="https://news.example.com/a/1")
    second = _article("a-2", source="web:host", url="https://news.example.com/a/1")
    composite = CompositeFeed([_StubFeed([first, second])])
    assert len(composite.fetch("Jane Doe")) == 2


def test_failing_sub_feed_is_isolated() -> None:
    composite = CompositeFeed(
        [_StubFeed([_article("a-1")]), _BoomFeed(), _StubFeed([_article("a-2")])]
    )
    articles = composite.fetch("Jane Doe")
    assert [a.article_id for a in articles] == ["a-1", "a-2"]


def test_all_sandbox_disabled_real_feeds_compose_to_empty(monkeypatch) -> None:
    for var in (
        "ADVERSE_MEDIA_RSS_ENABLED",
        "ADVERSE_MEDIA_WEB_ENABLED",
        "X_ADVERSE_MEDIA_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    composite = CompositeFeed(
        [RssAdverseMediaFeed(), WebSearchAdverseMediaFeed(), XAdverseMediaFeed()]
    )
    assert composite.fetch("Jane Doe", jurisdiction="GB") == []


def test_no_pii_in_logs_on_sub_feed_failure(caplog) -> None:
    composite = CompositeFeed([_BoomFeed()])
    with caplog.at_level("INFO"):
        composite.fetch("Very Secret Name")
    assert "Very Secret Name" not in caplog.text
