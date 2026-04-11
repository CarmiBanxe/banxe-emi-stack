"""
services/compliance_kb/ingestion/url_scraper.py — URL ingestion
IL-CKS-01 | banxe-emi-stack

Fetches web pages and extracts plain text for ingestion into the KB.
Uses httpx for fetching and BeautifulSoup4 for HTML parsing.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from services.compliance_kb.ingestion.chunker import chunk_text
from services.compliance_kb.storage.models import DocumentChunk

logger = logging.getLogger("banxe.compliance_kb.url_scraper")

# Tags whose content is stripped entirely
_SKIP_TAGS = frozenset(["script", "style", "nav", "header", "footer", "aside", "form"])


# ── Public API ─────────────────────────────────────────────────────────────


async def scrape_url(
    url: str,
    document_id: str,
    section: str = "Web",
    metadata: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> list[DocumentChunk]:
    """Fetch a URL and return DocumentChunk objects.

    Args:
        url: The URL to fetch (HTTP/HTTPS).
        document_id: ID to assign to all chunks.
        section: Section label for the content.
        metadata: Extra metadata propagated to chunks.
        timeout: HTTP request timeout in seconds.

    Returns:
        List of DocumentChunk objects.

    Raises:
        ValueError: If the URL cannot be fetched or parsed.
    """
    text = await _fetch_and_extract(url, timeout)
    if not text or not text.strip():
        raise ValueError(f"No text extracted from URL: {url}")

    meta = dict(metadata or {})
    meta["source_url"] = url

    return chunk_text(
        text=text,
        document_id=document_id,
        section=section,
        metadata=meta,
    )


async def fetch_url_text(url: str, timeout: float = 30.0) -> str:
    """Fetch a URL and return its plain text content (no chunking).

    Useful for previewing content before ingestion.
    """
    return await _fetch_and_extract(url, timeout)


# ── Internal ───────────────────────────────────────────────────────────────


async def _fetch_and_extract(url: str, timeout: float) -> str:
    """Fetch URL and extract plain text from HTML."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Banxe-ComplianceKB/1.0 (regulatory-research)"},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type or "application/xhtml" in content_type:
                return _extract_html_text(response.text)
            elif "text/plain" in content_type or "text/markdown" in content_type:
                return response.text
            else:
                # Try HTML extraction anyway
                return _extract_html_text(response.text)

    except ImportError:
        raise ValueError("httpx not installed — install httpx to use URL scraper")
    except Exception as exc:
        logger.warning("Failed to fetch URL %s: %s", url, exc)
        raise ValueError(f"Failed to fetch URL {url}: {exc}") from exc


def _extract_html_text(html: str) -> str:
    """Extract plain text from HTML using BeautifulSoup4."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags
        for tag in soup(_SKIP_TAGS):
            tag.decompose()

        # Extract text from main content areas
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id=re.compile(r"content|main|article", re.I))
            or soup.find("body")
            or soup
        )

        text = main.get_text(separator=" ", strip=True)
        # Normalise whitespace
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text.strip()

    except ImportError:
        logger.warning("BeautifulSoup4 not installed — falling back to regex extraction")
        return _regex_strip_html(html)


def _regex_strip_html(html: str) -> str:
    """Simple regex-based HTML stripping (BeautifulSoup4 fallback)."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()
