"""Tests for services.adverse_media.rss_feed.RssAdverseMediaFeed.

Locks in: SANDBOX-off contract (inert by default), Protocol compatibility,
degrade-to-[] on error, XXE safety (malicious entity XML must be rejected,
never resolved), entry→article mapping, and no PII in logs.
"""

from __future__ import annotations

import httpx

from services.adverse_media.models import NegativeNewsFeed
from services.adverse_media.rss_feed import RssAdverseMediaFeed

_RSS_OK = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>Court Reports</title>
  <item>
    <title>Jane Doe charged in fraud investigation</title>
    <link>https://news.example.com/a/1</link>
    <guid>https://news.example.com/a/1</guid>
    <pubDate>Mon, 20 Jul 2026 10:00:00 GMT</pubDate>
    <description>Jane Doe appeared in court over an alleged fraud scheme.</description>
  </item>
  <item>
    <title>Unrelated market update</title>
    <link>https://news.example.com/a/2</link>
    <guid>https://news.example.com/a/2</guid>
    <description>Nothing about the subject here.</description>
  </item>
</channel></rss>"""

# XXE payloads: internal entity expansion + external (file://) entity reference.
_RSS_XXE_INTERNAL = b"""<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY leak "SECRETDATA">]>
<rss version="2.0"><channel>
  <item><title>Jane Doe &leak;</title><description>Jane Doe &leak;</description></item>
</channel></rss>"""

_RSS_XXE_EXTERNAL = b"""<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<rss version="2.0"><channel>
  <item><title>Jane Doe &xxe;</title><description>Jane Doe &xxe;</description></item>
</channel></rss>"""


def _feed_with(body: bytes, status_code: int = 200) -> RssAdverseMediaFeed:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, content=body))
    return RssAdverseMediaFeed(
        enabled=True, urls=["https://news.example.com/rss"], transport=transport
    )


def test_disabled_by_default_returns_empty(monkeypatch) -> None:
    monkeypatch.delenv("ADVERSE_MEDIA_RSS_ENABLED", raising=False)
    monkeypatch.setenv("ADVERSE_MEDIA_RSS_URLS", "https://news.example.com/rss")
    feed = RssAdverseMediaFeed()
    assert feed.fetch("Jane Doe", jurisdiction="GB") == []


def test_enabled_but_no_urls_returns_empty(monkeypatch) -> None:
    monkeypatch.setenv("ADVERSE_MEDIA_RSS_ENABLED", "1")
    monkeypatch.delenv("ADVERSE_MEDIA_RSS_URLS", raising=False)
    feed = RssAdverseMediaFeed()
    assert feed.fetch("Jane Doe") == []


def test_explicit_disabled_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("ADVERSE_MEDIA_RSS_ENABLED", "1")
    monkeypatch.setenv("ADVERSE_MEDIA_RSS_URLS", "https://news.example.com/rss")
    feed = RssAdverseMediaFeed(enabled=False)
    assert feed.fetch("Jane Doe") == []


def test_implements_negative_news_feed_protocol() -> None:
    feed: NegativeNewsFeed = RssAdverseMediaFeed()
    assert callable(feed.fetch)


def test_maps_relevant_entries_to_articles() -> None:
    feed = _feed_with(_RSS_OK)
    articles = feed.fetch("Jane Doe", jurisdiction="GB")
    assert len(articles) == 1  # unrelated entry filtered out
    art = articles[0]
    assert art.article_id == "rss:news.example.com:https://news.example.com/a/1"
    assert art.subject_name == "Jane Doe"
    assert art.headline == "Jane Doe charged in fraud investigation"
    assert art.source == "rss:news.example.com"
    assert art.categories == ["rss-osint"]
    assert art.subject_jurisdiction == "GB"
    assert art.url == "https://news.example.com/a/1"
    assert art.published is not None
    assert art.snippet is not None


def test_xxe_internal_entity_is_rejected_not_expanded() -> None:
    feed = _feed_with(_RSS_XXE_INTERNAL)
    articles = feed.fetch("Jane Doe")
    assert articles == []  # rejected outright — malicious XML never reaches mapping
    assert all("SECRETDATA" not in (a.headline or "") for a in articles)


def test_xxe_external_entity_is_rejected() -> None:
    feed = _feed_with(_RSS_XXE_EXTERNAL)
    assert feed.fetch("Jane Doe") == []


def test_http_error_degrades_to_empty() -> None:
    feed = _feed_with(b"server error", status_code=500)
    assert feed.fetch("Jane Doe") == []


def test_transport_exception_degrades_to_empty() -> None:
    def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    feed = RssAdverseMediaFeed(
        enabled=True,
        urls=["https://news.example.com/rss"],
        transport=httpx.MockTransport(_raise),
    )
    assert feed.fetch("Jane Doe") == []


def test_one_bad_url_does_not_break_other_urls() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "bad.example.com":
            return httpx.Response(500, content=b"nope")
        return httpx.Response(200, content=_RSS_OK)

    feed = RssAdverseMediaFeed(
        enabled=True,
        urls=["https://bad.example.com/rss", "https://news.example.com/rss"],
        transport=httpx.MockTransport(_handler),
    )
    assert len(feed.fetch("Jane Doe")) == 1


def test_no_pii_in_logs_when_disabled(monkeypatch, caplog) -> None:
    monkeypatch.delenv("ADVERSE_MEDIA_RSS_ENABLED", raising=False)
    feed = RssAdverseMediaFeed()
    with caplog.at_level("INFO"):
        feed.fetch("Very Secret Name")
    assert "Very Secret Name" not in caplog.text
