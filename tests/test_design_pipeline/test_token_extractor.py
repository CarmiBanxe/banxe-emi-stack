"""
tests/test_design_pipeline/test_token_extractor.py
IL-D2C-01 — Design token extraction + Style Dictionary tests
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.design_pipeline.models import (
    ColorToken,
    DesignTokenSet,
    SpacingToken,
    TypographyToken,
)
from services.design_pipeline.penpot_client import InMemoryPenpotClient
from services.design_pipeline.token_extractor import TokenExtractionError, TokenExtractor


@pytest.fixture
def penpot_client() -> InMemoryPenpotClient:
    return InMemoryPenpotClient()


@pytest.fixture
def extractor(penpot_client: InMemoryPenpotClient, tmp_path: Path) -> TokenExtractor:
    return TokenExtractor(
        penpot_client=penpot_client,
        output_dir=tmp_path / "output",
        style_dict_cli="echo 'mock style-dict'",  # Mock CLI for tests
    )


class TestTokenExtractor:
    @pytest.mark.asyncio
    async def test_extract_from_penpot_returns_token_set(self, extractor: TokenExtractor) -> None:
        token_set = await extractor.extract_from_penpot("file-test-001")
        assert isinstance(token_set, DesignTokenSet)
        assert token_set.file_id == "file-test-001"

    @pytest.mark.asyncio
    async def test_extract_returns_colors(self, extractor: TokenExtractor) -> None:
        token_set = await extractor.extract_from_penpot("file-test-001")
        assert len(token_set.colors) > 0
        assert all(isinstance(c, ColorToken) for c in token_set.colors)

    @pytest.mark.asyncio
    async def test_extract_returns_spacing(self, extractor: TokenExtractor) -> None:
        token_set = await extractor.extract_from_penpot("file-test-001")
        assert len(token_set.spacing) > 0
        assert all(isinstance(s, SpacingToken) for s in token_set.spacing)

    @pytest.mark.asyncio
    async def test_extract_returns_typography(self, extractor: TokenExtractor) -> None:
        token_set = await extractor.extract_from_penpot("file-test-001")
        assert len(token_set.typography) > 0
        assert all(isinstance(t, TypographyToken) for t in token_set.typography)

    def test_export_to_style_dictionary_writes_file(
        self, extractor: TokenExtractor, tmp_path: Path
    ) -> None:
        """export_to_style_dictionary writes valid JSON."""
        token_set = DesignTokenSet(file_id="file-001")
        token_set.colors = [ColorToken(name="primary", value="#1A73E8")]
        token_set.spacing = [SpacingToken(name="md", value="16px")]

        # Redirect to temp file
        tokens_file = tmp_path / "banxe-tokens.json"
        import services.design_pipeline.token_extractor as mod

        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            result_path = extractor.export_to_style_dictionary(token_set)
        finally:
            mod._BANXE_TOKENS_FILE = orig

        assert result_path.exists()
        with result_path.open() as f:
            data = json.load(f)
        assert "color" in data
        assert data["color"]["primary"]["value"] == "#1A73E8"

    def test_export_preserves_spacing_tokens(
        self, extractor: TokenExtractor, tmp_path: Path
    ) -> None:
        token_set = DesignTokenSet(file_id="file-001")
        token_set.spacing = [
            SpacingToken(name="xs", value="4px"),
            SpacingToken(name="sm", value="8px"),
        ]

        tokens_file = tmp_path / "banxe-tokens.json"
        import services.design_pipeline.token_extractor as mod

        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            extractor.export_to_style_dictionary(token_set)
        finally:
            mod._BANXE_TOKENS_FILE = orig

        with tokens_file.open() as f:
            data = json.load(f)
        assert data["spacing"]["xs"]["value"] == "4px"
        assert data["spacing"]["sm"]["value"] == "8px"

    def test_get_css_variable_conversion(self) -> None:
        result = TokenExtractor.get_css_variable("color.primary")
        assert result == "var(--banxe-color-primary)"

    def test_get_css_variable_nested(self) -> None:
        result = TokenExtractor.get_css_variable("typography.heading-1")
        assert result == "var(--banxe-typography-heading-1)"

    def test_get_css_variable_spacing(self) -> None:
        result = TokenExtractor.get_css_variable("spacing.md")
        assert result == "var(--banxe-spacing-md)"

    @pytest.mark.asyncio
    async def test_sync_returns_token_sync_result(
        self, extractor: TokenExtractor, tmp_path: Path
    ) -> None:
        import services.design_pipeline.token_extractor as mod

        tokens_file = tmp_path / "banxe-tokens.json"
        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            result = await extractor.sync("file-test-001")
        finally:
            mod._BANXE_TOKENS_FILE = orig

        assert result.file_id == "file-test-001"
        assert result.tokens_extracted >= 0  # InMemory may return 0+ tokens

    @pytest.mark.asyncio
    async def test_sync_reports_tokens_count(
        self, extractor: TokenExtractor, tmp_path: Path
    ) -> None:
        import services.design_pipeline.token_extractor as mod

        tokens_file = tmp_path / "banxe-tokens.json"
        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            result = await extractor.sync("file-test-001")
        finally:
            mod._BANXE_TOKENS_FILE = orig

        # InMemory client returns 3 colors + 3 spacing + 1 typography = 7 tokens
        assert result.tokens_extracted == 7

    def test_token_count_from_static_file(self) -> None:
        """token_count() reads from disk — graceful when file missing."""
        count = TokenExtractor.token_count()
        assert isinstance(count, int)
        assert count >= 0

    def test_load_current_tokens_when_missing(self, tmp_path: Path) -> None:
        import services.design_pipeline.token_extractor as mod

        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tmp_path / "nonexistent.json"
        try:
            result = TokenExtractor.load_current_tokens()
        finally:
            mod._BANXE_TOKENS_FILE = orig

        assert result == {}


class TestTokenExtractionError:
    def test_extraction_error_has_context(self) -> None:
        err = TokenExtractionError("test error", context={"file_id": "f1"})
        assert str(err) == "test error"
        assert err.context == {"file_id": "f1"}

    def test_extraction_error_empty_context(self) -> None:
        err = TokenExtractionError("no context")
        assert err.context == {}
