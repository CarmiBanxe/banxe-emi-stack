"""
services/design_pipeline/penpot_client.py — Penpot REST API / MCP client
IL-D2C-01 | BANXE EMI AI Bank

Implements the PenpotPort protocol (hexagonal architecture).
All network I/O is async. No float for dimensions that feed financial forms.

Penpot REST API base: {base_url}/api/rpc/command/{method}
Auth: Bearer token via Authorization header.

References:
  https://help.penpot.app/technical-guide/developer/api/
  https://github.com/penpot/penpot
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from services.design_pipeline.models import (
    AutoLayoutConfig,
    ColorToken,
    Component,
    ComponentListEntry,
    DesignLayer,
    DesignTokenSet,
    ExportFormat,
    LayoutType,
    PageTree,
    SpacingToken,
    TypographyToken,
)

logger = logging.getLogger("banxe.design_pipeline.penpot")


class PenpotPort(Protocol):
    """Hexagonal port — any Penpot client must satisfy this interface."""

    async def get_project_files(self, project_id: str) -> list[dict[str, Any]]: ...

    async def get_file_components(self, file_id: str) -> list[Component]: ...

    async def get_design_tokens(self, file_id: str) -> DesignTokenSet: ...

    async def get_page_structure(self, file_id: str, page_id: str) -> PageTree: ...

    async def get_component_svg(self, file_id: str, component_id: str) -> str: ...

    async def export_frame(self, file_id: str, frame_id: str, format: ExportFormat) -> bytes: ...

    async def get_component_context(self, component_id: str) -> dict[str, Any]: ...

    async def list_components_flat(self, file_id: str) -> list[ComponentListEntry]: ...


# ── Penpot MCP Client (live) ─────────────────────────────────────────────────


class PenpotMCPClient:
    """
    Client for Penpot REST API.

    Penpot's REST API is RPC-based:
      POST /api/rpc/command/<method>
      Authorization: Token <access_token>

    Args:
        base_url: Penpot instance URL, e.g. http://localhost:9001
        token:    Penpot access token (from Profile → Access Tokens)
        timeout:  HTTP timeout in seconds
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def _rpc_url(self, method: str) -> str:
        return f"{self._base_url}/api/rpc/command/{method}"

    async def _get(self, method: str, params: dict[str, Any] | None = None) -> Any:
        url = self._rpc_url(method)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, headers=self._headers, params=params or {})
            r.raise_for_status()
            return r.json()

    async def _post(self, method: str, data: dict[str, Any]) -> Any:
        url = self._rpc_url(method)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(url, headers=self._headers, json=data)
            r.raise_for_status()
            return r.json()

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_project_files(self, project_id: str) -> list[dict[str, Any]]:
        """List all files in a Penpot project."""
        data = await self._get("get-project-files", {"project-id": project_id})
        return data if isinstance(data, list) else data.get("files", [])

    async def get_file_components(self, file_id: str) -> list[Component]:
        """Return all reusable components from a Penpot file."""
        data = await self._get("get-file", {"id": file_id})
        raw_components = data.get("data", {}).get("components", {})
        components: list[Component] = []
        for comp_id, comp_data in raw_components.items():
            components.append(
                Component(
                    id=comp_id,
                    name=comp_data.get("name", ""),
                    file_id=file_id,
                    page_id=comp_data.get("main-instance-page-id", ""),
                    path=comp_data.get("path", ""),
                    annotations=comp_data.get("annotation", {}),
                )
            )
        return components

    async def get_design_tokens(self, file_id: str) -> DesignTokenSet:
        """
        Extract design tokens from a Penpot file.

        Penpot stores tokens in the file's :tokens key (2025+ format).
        Falls back to parsing the component library for colours/typography.
        """
        data = await self._get("get-file", {"id": file_id})
        file_data = data.get("data", {})

        token_set = DesignTokenSet(file_id=file_id, raw=file_data)

        # --- Native Penpot tokens (2025+) ---
        native_tokens: dict[str, Any] = file_data.get("tokens", {})
        for token_name, token_def in native_tokens.items():
            category = token_def.get("type", "")
            value = token_def.get("value", "")
            if category == "color":
                token_set.colors.append(ColorToken(name=token_name, value=str(value)))
            elif category == "spacing":
                token_set.spacing.append(SpacingToken(name=token_name, value=str(value)))

        # --- Fallback: parse colours from file colors ---
        colors_raw: list[dict[str, Any]] = file_data.get("colors", [])
        for color in colors_raw:
            cname = color.get("name", "")
            chex = color.get("color", "#000000")
            if cname and not any(c.name == cname for c in token_set.colors):
                token_set.colors.append(ColorToken(name=cname, value=chex))

        # --- Fallback: parse typography from typographies ---
        typographies_raw: list[dict[str, Any]] = file_data.get("typographies", [])
        for typo in typographies_raw:
            tname = typo.get("name", "")
            fonts = typo.get("fonts", [{}])
            f = fonts[0] if fonts else {}
            token_set.typography.append(
                TypographyToken(
                    name=tname,
                    font_family=f.get("font-family", "Inter"),
                    font_size=f.get("font-size", "16px"),
                    font_weight=int(f.get("font-weight", 400)),
                    line_height=f.get("line-height", 1.5),
                    letter_spacing=f.get("letter-spacing", "0px"),
                )
            )

        return token_set

    async def get_page_structure(self, file_id: str, page_id: str) -> PageTree:
        """Return the full layer hierarchy of a Penpot page."""
        data = await self._get("get-file", {"id": file_id})
        pages_raw: dict[str, Any] = data.get("data", {}).get("pages-index", {})
        page_raw = pages_raw.get(page_id, {})
        page_name = page_raw.get("name", page_id)

        root_layer = self._parse_layer(
            page_raw.get("objects", {}).get("uuid-00000000-0000-0000-0000-000000000000", {})
        )
        return PageTree(
            file_id=file_id,
            page_id=page_id,
            page_name=page_name,
            root=root_layer,
        )

    async def get_component_svg(self, file_id: str, component_id: str) -> str:
        """Export a component as SVG string."""
        raw: bytes = await self.export_frame(file_id, component_id, ExportFormat.SVG)
        return raw.decode("utf-8", errors="replace")

    async def export_frame(self, file_id: str, frame_id: str, format: ExportFormat) -> bytes:
        """Export a frame/component as bytes (SVG, PNG, or PDF)."""
        url = f"{self._base_url}/api/export"
        params = {
            "file-id": file_id,
            "object-id": frame_id,
            "type": format.value,
            "scale": 2,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, headers=self._headers, params=params)
            r.raise_for_status()
            return r.content

    async def get_component_context(self, component_id: str) -> dict[str, Any]:
        """
        Build a structured context dict for LLM prompting.

        Returns a simplified JSON representation of the component's
        layout, styling, and content hierarchy.
        """
        # In production, this would call get_file_components + get_page_structure.
        # For now we return a structured stub that the LLM can reason about.
        return {
            "component_id": component_id,
            "name": "Component",
            "layout": "flex-col",
            "children": [],
            "tokens_in_use": [],
        }

    async def list_components_flat(self, file_id: str) -> list[ComponentListEntry]:
        """Return flat list of all components for a file (for API listing)."""
        components = await self.get_file_components(file_id)
        return [
            ComponentListEntry(
                id=c.id,
                name=c.name,
                path=c.path,
                file_id=c.file_id,
                thumbnail_url=c.thumbnail_url,
            )
            for c in components
        ]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_layer(self, obj: dict[str, Any]) -> DesignLayer:
        """Recursively parse a Penpot layer object into a DesignLayer."""
        # Note: child IDs (obj.get("shapes", [])) not resolved here; full resolution
        # requires passing the full objects map. Simplified for scaffold.
        return DesignLayer(
            id=obj.get("id", ""),
            name=obj.get("name", ""),
            layer_type=obj.get("type", "frame"),
            x=float(obj.get("x", 0)),
            y=float(obj.get("y", 0)),
            width=float(obj.get("width", 0)),
            height=float(obj.get("height", 0)),
            fill_color=self._extract_fill_color(obj),
            opacity=float(obj.get("opacity", 1.0)),
            visible=obj.get("hidden", False) is False,
            border_radius=float(obj.get("rx", 0)),
            text_content=obj.get("content", {})
            .get("children", [{}])[0]
            .get("children", [{}])[0]
            .get("text", "")
            if obj.get("type") == "text"
            else "",
            layout=LayoutType.FLEX_ROW if obj.get("layout") == "flex" else LayoutType.ABSOLUTE,
            auto_layout=self._parse_auto_layout(obj) if obj.get("layout") == "flex" else None,
        )

    @staticmethod
    def _extract_fill_color(obj: dict[str, Any]) -> str:
        fills = obj.get("fills", [])
        if fills and "fill-color" in fills[0]:
            return fills[0]["fill-color"]
        return ""

    @staticmethod
    def _parse_auto_layout(obj: dict[str, Any]) -> AutoLayoutConfig:
        direction = obj.get("layout-flex-dir", "row")
        gap = obj.get("layout-gap", {})
        gap_px = f"{gap.get('row-gap', 0)}px" if isinstance(gap, dict) else "0px"
        padding = obj.get("layout-padding", {})
        if isinstance(padding, dict):
            pt = f"{padding.get('p1', 0)}px"
            pr = f"{padding.get('p2', 0)}px"
            pb = f"{padding.get('p3', 0)}px"
            pl = f"{padding.get('p4', 0)}px"
        else:
            pt = pr = pb = pl = "0px"
        return AutoLayoutConfig(
            direction=direction,
            gap=gap_px,
            padding_top=pt,
            padding_right=pr,
            padding_bottom=pb,
            padding_left=pl,
            justify_content=obj.get("layout-justify-content", "flex-start"),
            align_items=obj.get("layout-align-items", "flex-start"),
        )


# ── InMemory stub for tests ───────────────────────────────────────────────────


class InMemoryPenpotClient:
    """
    Test double — implements PenpotPort without any network calls.

    Pre-populated with deterministic data suitable for unit tests.
    """

    def __init__(self) -> None:
        self._file_id = "file-test-001"
        self._page_id = "page-test-001"

    async def get_project_files(self, project_id: str) -> list[dict[str, Any]]:
        return [{"id": self._file_id, "name": "BANXE Design System", "projectId": project_id}]

    async def get_file_components(self, file_id: str) -> list[Component]:
        return [
            Component(
                id="comp-button-001",
                name="PrimaryButton",
                file_id=file_id,
                page_id=self._page_id,
                path="Atoms/Buttons",
                description="Primary CTA button",
            ),
            Component(
                id="comp-input-001",
                name="TextInput",
                file_id=file_id,
                page_id=self._page_id,
                path="Atoms/Inputs",
                description="Standard text input",
            ),
            Component(
                id="comp-kyc-form-001",
                name="KYCForm",
                file_id=file_id,
                page_id=self._page_id,
                path="Forms/KYC",
                description="KYC onboarding form",
                is_kyc_component=True,
            ),
        ]

    async def get_design_tokens(self, file_id: str) -> DesignTokenSet:
        token_set = DesignTokenSet(file_id=file_id)
        token_set.colors = [
            ColorToken(name="primary", value="#1A73E8"),
            ColorToken(name="secondary", value="#34A853"),
            ColorToken(name="danger", value="#EA4335"),
        ]
        token_set.spacing = [
            SpacingToken(name="sm", value="8px"),
            SpacingToken(name="md", value="16px"),
            SpacingToken(name="lg", value="24px"),
        ]
        token_set.typography = [
            TypographyToken(
                name="body",
                font_family="Inter",
                font_size="16px",
                font_weight=400,
                line_height=1.5,
            )
        ]
        return token_set

    async def get_page_structure(self, file_id: str, page_id: str) -> PageTree:
        root = DesignLayer(
            id="root",
            name="Page",
            layer_type="frame",
            width=1440.0,
            height=900.0,
        )
        return PageTree(
            file_id=file_id,
            page_id=page_id,
            page_name="Dashboard",
            root=root,
        )

    async def get_component_svg(self, file_id: str, component_id: str) -> str:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40">'
            '<rect width="120" height="40" rx="8" fill="#1A73E8"/>'
            '<text x="60" y="25" text-anchor="middle" fill="white">Button</text>'
            "</svg>"
        )

    async def export_frame(self, file_id: str, frame_id: str, format: ExportFormat) -> bytes:
        svg = await self.get_component_svg(file_id, frame_id)
        return svg.encode("utf-8")

    async def get_component_context(self, component_id: str) -> dict[str, Any]:
        return {
            "component_id": component_id,
            "name": "PrimaryButton",
            "layout": "flex-row",
            "width": 120,
            "height": 40,
            "background": "#1A73E8",
            "border_radius": 8,
            "children": [
                {"type": "text", "content": "Click me", "color": "#FFFFFF", "font_size": "16px"}
            ],
            "tokens_in_use": ["color.primary", "spacing.md", "typography.body"],
        }

    async def list_components_flat(self, file_id: str) -> list[ComponentListEntry]:
        components = await self.get_file_components(file_id)
        return [
            ComponentListEntry(
                id=c.id,
                name=c.name,
                path=c.path,
                file_id=c.file_id,
            )
            for c in components
        ]
