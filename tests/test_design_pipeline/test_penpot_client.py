"""
tests/test_design_pipeline/test_penpot_client.py
IL-D2C-01 — Penpot API/MCP client tests (InMemory stubs — no network)
"""

from __future__ import annotations

import pytest

from services.design_pipeline.models import (
    Component,
    ComponentListEntry,
    DesignTokenSet,
    ExportFormat,
    PageTree,
)
from services.design_pipeline.penpot_client import InMemoryPenpotClient


@pytest.fixture
def client() -> InMemoryPenpotClient:
    return InMemoryPenpotClient()


class TestInMemoryPenpotClient:
    """All tests use InMemoryPenpotClient — zero network dependency."""

    @pytest.mark.asyncio
    async def test_get_project_files_returns_list(self, client: InMemoryPenpotClient) -> None:
        files = await client.get_project_files("project-001")
        assert isinstance(files, list)
        assert len(files) == 1
        assert files[0]["id"] == "file-test-001"
        assert files[0]["projectId"] == "project-001"

    @pytest.mark.asyncio
    async def test_get_file_components_returns_components(
        self, client: InMemoryPenpotClient
    ) -> None:
        components = await client.get_file_components("file-test-001")
        assert len(components) == 3
        assert all(isinstance(c, Component) for c in components)

    @pytest.mark.asyncio
    async def test_get_file_components_kyc_flag(self, client: InMemoryPenpotClient) -> None:
        components = await client.get_file_components("file-test-001")
        kyc_comps = [c for c in components if c.is_kyc_component]
        assert len(kyc_comps) == 1
        assert kyc_comps[0].name == "KYCForm"

    @pytest.mark.asyncio
    async def test_get_file_components_paths(self, client: InMemoryPenpotClient) -> None:
        components = await client.get_file_components("file-test-001")
        paths = {c.path for c in components}
        assert "Atoms/Buttons" in paths
        assert "Atoms/Inputs" in paths
        assert "Forms/KYC" in paths

    @pytest.mark.asyncio
    async def test_get_design_tokens_returns_token_set(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        assert isinstance(tokens, DesignTokenSet)
        assert tokens.file_id == "file-test-001"

    @pytest.mark.asyncio
    async def test_design_tokens_colors(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        assert len(tokens.colors) == 3
        color_names = [c.name for c in tokens.colors]
        assert "primary" in color_names
        assert "secondary" in color_names
        assert "danger" in color_names

    @pytest.mark.asyncio
    async def test_design_tokens_spacing(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        assert len(tokens.spacing) == 3
        spacing_names = [s.name for s in tokens.spacing]
        assert "md" in spacing_names

    @pytest.mark.asyncio
    async def test_design_tokens_typography(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        assert len(tokens.typography) == 1
        assert tokens.typography[0].name == "body"
        assert tokens.typography[0].font_size == "16px"

    @pytest.mark.asyncio
    async def test_get_page_structure_returns_page_tree(self, client: InMemoryPenpotClient) -> None:
        page_tree = await client.get_page_structure("file-test-001", "page-test-001")
        assert isinstance(page_tree, PageTree)
        assert page_tree.file_id == "file-test-001"
        assert page_tree.page_id == "page-test-001"
        assert page_tree.root is not None

    @pytest.mark.asyncio
    async def test_get_page_structure_root_dimensions(self, client: InMemoryPenpotClient) -> None:
        page_tree = await client.get_page_structure("file-test-001", "page-test-001")
        root = page_tree.root
        assert root is not None
        assert root.width == 1440.0
        assert root.height == 900.0

    @pytest.mark.asyncio
    async def test_get_component_svg_returns_svg_string(self, client: InMemoryPenpotClient) -> None:
        svg = await client.get_component_svg("file-test-001", "comp-button-001")
        assert isinstance(svg, str)
        assert "<svg" in svg
        assert "fill=" in svg

    @pytest.mark.asyncio
    async def test_export_frame_svg_returns_bytes(self, client: InMemoryPenpotClient) -> None:
        data = await client.export_frame("file-test-001", "comp-button-001", ExportFormat.SVG)
        assert isinstance(data, bytes)
        assert b"<svg" in data

    @pytest.mark.asyncio
    async def test_get_component_context_returns_dict(self, client: InMemoryPenpotClient) -> None:
        ctx = await client.get_component_context("comp-button-001")
        assert isinstance(ctx, dict)
        assert "component_id" in ctx
        assert "name" in ctx
        assert "layout" in ctx

    @pytest.mark.asyncio
    async def test_get_component_context_tokens_in_use(self, client: InMemoryPenpotClient) -> None:
        ctx = await client.get_component_context("comp-button-001")
        assert "tokens_in_use" in ctx
        assert "color.primary" in ctx["tokens_in_use"]

    @pytest.mark.asyncio
    async def test_list_components_flat_returns_entries(self, client: InMemoryPenpotClient) -> None:
        entries = await client.list_components_flat("file-test-001")
        assert len(entries) == 3
        assert all(isinstance(e, ComponentListEntry) for e in entries)

    @pytest.mark.asyncio
    async def test_list_components_flat_has_ids(self, client: InMemoryPenpotClient) -> None:
        entries = await client.list_components_flat("file-test-001")
        ids = {e.id for e in entries}
        assert "comp-button-001" in ids
        assert "comp-input-001" in ids

    @pytest.mark.asyncio
    async def test_get_project_files_different_project_ids(
        self, client: InMemoryPenpotClient
    ) -> None:
        """Returns same file regardless of project_id (InMemory behaviour)."""
        files_a = await client.get_project_files("project-alpha")
        files_b = await client.get_project_files("project-beta")
        assert len(files_a) == len(files_b)


class TestDesignTokenSetSerialization:
    """Test DesignTokenSet.to_style_dictionary_format()."""

    @pytest.mark.asyncio
    async def test_style_dictionary_format_has_color_key(
        self, client: InMemoryPenpotClient
    ) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        sd = tokens.to_style_dictionary_format()
        assert "color" in sd

    @pytest.mark.asyncio
    async def test_style_dictionary_format_color_values(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        sd = tokens.to_style_dictionary_format()
        assert sd["color"]["primary"]["value"] == "#1A73E8"

    @pytest.mark.asyncio
    async def test_style_dictionary_format_spacing(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        sd = tokens.to_style_dictionary_format()
        assert "spacing" in sd
        assert sd["spacing"]["md"]["value"] == "16px"

    @pytest.mark.asyncio
    async def test_style_dictionary_format_typography(self, client: InMemoryPenpotClient) -> None:
        tokens = await client.get_design_tokens("file-test-001")
        sd = tokens.to_style_dictionary_format()
        assert "typography" in sd
        body = sd["typography"]["body"]
        assert "value" in body
        assert body["value"]["fontSize"] == "16px"
