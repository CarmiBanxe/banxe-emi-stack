"""
tests/test_compliance_kb/test_mcp_tools.py — MCP KB tool tests
IL-CKS-01 | banxe-emi-stack

Tests the 6 MCP KB tools by mocking httpx responses.
Tests: 10 scenarios covering each tool + error paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# Import the MCP tool functions from the server module
from banxe_mcp.server import (
    kb_compare_versions,
    kb_get_citations,
    kb_get_notebook,
    kb_list_notebooks,
    kb_query,
    kb_search,
)


def _mock_response(json_data, status_code: int = 200):
    """Build a mock httpx response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    if status_code >= 400:
        import httpx

        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=mock
        )
    return mock


class TestKbListNotebooks:
    async def test_lists_notebooks_successfully(self):
        """kb_list_notebooks returns formatted notebook list."""
        mock_data = [
            {
                "id": "emi-uk-fca",
                "name": "UK FCA Regulations",
                "jurisdiction": "uk",
                "doc_count": 42,
            },
            {"id": "emi-eu-aml", "name": "EU AML Framework", "jurisdiction": "eu", "doc_count": 0},
        ]
        with patch("banxe_mcp.server._api_get", new=AsyncMock(return_value=mock_data)):
            result = await kb_list_notebooks()
        assert "emi-uk-fca" in result
        assert "UK FCA Regulations" in result
        assert "42" in result

    async def test_lists_notebooks_empty(self):
        """kb_list_notebooks handles empty notebook list."""
        with patch("banxe_mcp.server._api_get", new=AsyncMock(return_value=[])):
            result = await kb_list_notebooks()
        assert "No compliance notebooks found" in result

    async def test_lists_notebooks_connect_error(self):
        """kb_list_notebooks returns error message on connection failure."""
        import httpx

        with patch(
            "banxe_mcp.server._api_get", new=AsyncMock(side_effect=httpx.ConnectError("down"))
        ):
            result = await kb_list_notebooks()
        assert "Error" in result


class TestKbGetNotebook:
    async def test_get_notebook_returns_details(self):
        """kb_get_notebook returns formatted notebook details."""
        mock_data = {
            "id": "emi-uk-fca",
            "name": "UK FCA Regulations",
            "jurisdiction": "uk",
            "tags": ["fca", "uk"],
            "description": "FCA handbook content",
            "doc_count": 100,
            "sources": [
                {
                    "id": "fca-cass-15",
                    "name": "CASS 15",
                    "source_type": "regulation",
                    "version": "2025-12-01",
                    "url": "https://handbook.fca.org.uk",
                }
            ],
        }
        with patch("banxe_mcp.server._api_get", new=AsyncMock(return_value=mock_data)):
            result = await kb_get_notebook("emi-uk-fca")
        assert "UK FCA Regulations" in result
        assert "CASS 15" in result
        assert "fca-cass-15" in result

    async def test_get_notebook_not_found(self):
        """kb_get_notebook handles 404 gracefully."""
        import httpx

        with patch(
            "banxe_mcp.server._api_get",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404", request=MagicMock(), response=_mock_response({}, 404)
                )
            ),
        ):
            result = await kb_get_notebook("nonexistent")
        assert "not found" in result.lower()


class TestKbQuery:
    async def test_query_returns_answer_with_citations(self):
        """kb_query returns answer text and citation list."""
        mock_data = {
            "question": "What is safeguarding?",
            "answer": "Safeguarding requires EMIs to protect client funds.",
            "notebook_id": "emi-uk-fca",
            "confidence": 0.85,
            "citations": [
                {
                    "source_id": "fca-cass-15",
                    "title": "CASS 15",
                    "section": "Article 5",
                    "snippet": "Client funds must be segregated.",
                    "version": "2025-12-01",
                    "uri": "https://handbook.fca.org.uk",
                }
            ],
        }
        with patch("banxe_mcp.server._api_post", new=AsyncMock(return_value=mock_data)):
            result = await kb_query("emi-uk-fca", "What is safeguarding?")
        assert "Safeguarding" in result
        assert "fca-cass-15" in result
        assert "Article 5" in result

    async def test_query_notebook_not_found(self):
        """kb_query returns not-found message for missing notebook."""
        import httpx

        with patch(
            "banxe_mcp.server._api_post",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404", request=MagicMock(), response=_mock_response({}, 404)
                )
            ),
        ):
            result = await kb_query("bad-notebook", "test question")
        assert "not found" in result.lower()


class TestKbSearch:
    async def test_search_returns_results(self):
        """kb_search returns formatted search results."""
        mock_data = [
            {
                "chunk_id": "doc-001::chunk-0000",
                "document_id": "fca-cass-15",
                "text": "EMIs must maintain segregated accounts for client funds.",
                "section": "Article 5",
                "score": 0.92,
            }
        ]
        with patch("banxe_mcp.server._api_post", new=AsyncMock(return_value=mock_data)):
            result = await kb_search("emi-uk-fca", "safeguarding accounts")
        assert "Article 5" in result
        assert "0.92" in result

    async def test_search_empty_results(self):
        """kb_search handles empty results gracefully."""
        with patch("banxe_mcp.server._api_post", new=AsyncMock(return_value=[])):
            result = await kb_search("emi-uk-fca", "very obscure query")
        assert "No results found" in result


class TestKbCompareVersions:
    async def test_compare_returns_diff(self):
        """kb_compare_versions returns structured diff output."""
        mock_data = {
            "source_id": "fca-cass-15",
            "from_version": "2021-01-01",
            "to_version": "2025-12-01",
            "diff_summary": "Found 2 changes.",
            "changes": [
                {
                    "section": "Article 5",
                    "change_type": "modified",
                    "before": "Old safeguarding text.",
                    "after": "New safeguarding text with PS25/12 requirements.",
                    "impact_tags": ["modified-requirement"],
                }
            ],
        }
        with patch("banxe_mcp.server._api_post", new=AsyncMock(return_value=mock_data)):
            result = await kb_compare_versions("fca-cass-15", "2021-01-01", "2025-12-01")
        assert "fca-cass-15" in result
        assert "MODIFIED" in result
        assert "Article 5" in result


class TestKbGetCitations:
    async def test_get_citations_returns_details(self):
        """kb_get_citations returns full citation metadata."""
        mock_data = {
            "source_id": "fca-cass-15",
            "source_type": "regulation",
            "title": "CASS 15 Safeguarding",
            "section": "Full Document",
            "snippet": "CASS 15 Safeguarding — regulation (2025-12-01)",
            "uri": "https://handbook.fca.org.uk",
            "version": "2025-12-01",
        }
        with patch("banxe_mcp.server._api_get", new=AsyncMock(return_value=mock_data)):
            result = await kb_get_citations("fca-cass-15", "emi-uk-fca")
        assert "CASS 15 Safeguarding" in result
        assert "regulation" in result
        assert "2025-12-01" in result

    async def test_get_citations_not_found(self):
        """kb_get_citations handles 404 gracefully."""
        import httpx

        with patch(
            "banxe_mcp.server._api_get",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404", request=MagicMock(), response=_mock_response({}, 404)
                )
            ),
        ):
            result = await kb_get_citations("nonexistent-src", "emi-uk-fca")
        assert "not found" in result.lower()
