"""Tests for services.adverse_media.web_feed.WebSearchAdverseMediaFeed.

Locks in: SANDBOX-off contract (inert by default — needs enable flag + URL +
token), Protocol compatibility, degrade-to-[] on error, result→article mapping,
and no PII in logs.
"""

from __future__ import annotations

import json

import httpx

from services.adverse_media.models import NegativeNewsFeed
from services.adverse_media.web_feed import WebSearchAdverseMediaFeed

_RESULTS = {
    "results": [
        {
            "id": "r-1",
            "title": "Jane Doe named in laundering probe",
            "url": "https://osint.example.org/story/1",
            "published": "2026-07-20",
            "snippet": "Investigators named Jane Doe in a laundering probe.",
        },
        {"title": "No url or id result", "snippet": "still mapped"},
    ]
}


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_ENABLED", "1")
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_SEARCH_URL", "https://search.example.net/api")
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_SEARCH_TOKEN", "dummy-token")


def test_disabled_by_default_returns_empty(monkeypatch) -> None:
    monkeypatch.delenv("ADVERSE_MEDIA_WEB_ENABLED", raising=False)
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_SEARCH_URL", "https://search.example.net/api")
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_SEARCH_TOKEN", "dummy-token")
    feed = WebSearchAdverseMediaFeed()
    assert feed.fetch("Jane Doe", jurisdiction="GB") == []


def test_enabled_but_no_url_returns_empty(monkeypatch) -> None:
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_ENABLED", "1")
    monkeypatch.delenv("ADVERSE_MEDIA_WEB_SEARCH_URL", raising=False)
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_SEARCH_TOKEN", "dummy-token")
    feed = WebSearchAdverseMediaFeed()
    assert feed.fetch("Jane Doe") == []


def test_enabled_but_no_token_returns_empty(monkeypatch) -> None:
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_ENABLED", "1")
    monkeypatch.setenv("ADVERSE_MEDIA_WEB_SEARCH_URL", "https://search.example.net/api")
    monkeypatch.delenv("ADVERSE_MEDIA_WEB_SEARCH_TOKEN", raising=False)
    feed = WebSearchAdverseMediaFeed()
    assert feed.fetch("Jane Doe") == []


def test_explicit_disabled_overrides_env(monkeypatch) -> None:
    _enable(monkeypatch)
    feed = WebSearchAdverseMediaFeed(enabled=False)
    assert feed.fetch("Jane Doe") == []


def test_implements_negative_news_feed_protocol() -> None:
    feed: NegativeNewsFeed = WebSearchAdverseMediaFeed()
    assert callable(feed.fetch)


def test_maps_results_to_articles(monkeypatch) -> None:
    _enable(monkeypatch)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(_RESULTS).encode())
    )
    feed = WebSearchAdverseMediaFeed(transport=transport)
    articles = feed.fetch("Jane Doe", jurisdiction="GB")
    assert len(articles) == 2
    art = articles[0]
    assert art.article_id == "web:r-1"
    assert art.subject_name == "Jane Doe"
    assert art.headline == "Jane Doe named in laundering probe"
    assert art.source == "web:osint.example.org"  # host of the result url
    assert art.categories == ["web-osint"]
    assert art.subject_jurisdiction == "GB"
    assert art.url == "https://osint.example.org/story/1"
    # result without its own url falls back to the search host as source
    assert articles[1].source == "web:search.example.net"


def test_http_error_degrades_to_empty(monkeypatch) -> None:
    _enable(monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(500, content=b"nope"))
    feed = WebSearchAdverseMediaFeed(transport=transport)
    assert feed.fetch("Jane Doe") == []


def test_invalid_json_degrades_to_empty(monkeypatch) -> None:
    _enable(monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json"))
    feed = WebSearchAdverseMediaFeed(transport=transport)
    assert feed.fetch("Jane Doe") == []


def test_non_dict_payload_degrades_to_empty(monkeypatch) -> None:
    _enable(monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"[1, 2]"))
    feed = WebSearchAdverseMediaFeed(transport=transport)
    assert feed.fetch("Jane Doe") == []


def test_no_pii_in_logs_when_disabled(monkeypatch, caplog) -> None:
    monkeypatch.delenv("ADVERSE_MEDIA_WEB_ENABLED", raising=False)
    feed = WebSearchAdverseMediaFeed()
    with caplog.at_level("INFO"):
        feed.fetch("Very Secret Name")
    assert "Very Secret Name" not in caplog.text
