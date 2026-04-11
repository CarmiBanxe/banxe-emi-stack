"""
services/design_pipeline/models.py — Domain models for Design-to-Code Pipeline
IL-D2C-01 | BANXE EMI AI Bank

All models are Pydantic v2 dataclasses or BaseModel subclasses.
No float for any values that could become monetary — use Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

# ── Enumerations ─────────────────────────────────────────────────────────────


class Framework(str, Enum):
    REACT = "react"
    VUE = "vue"
    REACT_NATIVE = "react-native"
    ANGULAR = "angular"
    SVELTE = "svelte"


class ExportFormat(str, Enum):
    SVG = "svg"
    PNG = "png"
    PDF = "pdf"


class QAStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"
    SKIPPED = "skipped"


class LayoutType(str, Enum):
    FLEX_ROW = "flex-row"
    FLEX_COL = "flex-col"
    GRID = "grid"
    ABSOLUTE = "absolute"
    FIXED = "fixed"


class TokenCategory(str, Enum):
    COLOR = "color"
    TYPOGRAPHY = "typography"
    SPACING = "spacing"
    BORDER_RADIUS = "border-radius"
    SHADOW = "shadow"
    ANIMATION = "animation"


# ── Design Token Models ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ColorToken:
    name: str
    value: str  # Hex or rgba string
    comment: str = ""
    category: TokenCategory = TokenCategory.COLOR


@dataclass(frozen=True)
class TypographyToken:
    name: str
    font_family: str
    font_size: str
    font_weight: int
    line_height: float | str
    letter_spacing: str = "0px"
    comment: str = ""
    category: TokenCategory = TokenCategory.TYPOGRAPHY


@dataclass(frozen=True)
class SpacingToken:
    name: str
    value: str  # CSS size string e.g. "16px"
    category: TokenCategory = TokenCategory.SPACING


@dataclass(frozen=True)
class ShadowToken:
    name: str
    value: str  # CSS box-shadow string
    category: TokenCategory = TokenCategory.SHADOW


@dataclass
class DesignTokenSet:
    """Complete set of design tokens extracted from Penpot."""

    file_id: str
    colors: list[ColorToken] = field(default_factory=list)
    typography: list[TypographyToken] = field(default_factory=list)
    spacing: list[SpacingToken] = field(default_factory=list)
    shadows: list[ShadowToken] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_style_dictionary_format(self) -> dict[str, Any]:
        """Convert to Style Dictionary JSON format."""
        result: dict[str, Any] = {}

        result["color"] = {t.name: {"value": t.value, "comment": t.comment} for t in self.colors}

        result["typography"] = {
            t.name: {
                "value": {
                    "fontFamily": t.font_family,
                    "fontSize": t.font_size,
                    "fontWeight": t.font_weight,
                    "lineHeight": t.line_height,
                    "letterSpacing": t.letter_spacing,
                }
            }
            for t in self.typography
        }

        result["spacing"] = {t.name: {"value": t.value} for t in self.spacing}

        result["shadow"] = {t.name: {"value": t.value} for t in self.shadows}

        return result


# ── Component / Layout Models ─────────────────────────────────────────────────


@dataclass(frozen=True)
class LayoutConstraint:
    horizontal: str = "left"  # left | right | center | scale | stretch
    vertical: str = "top"  # top | bottom | center | scale | stretch


@dataclass
class AutoLayoutConfig:
    direction: str = "row"  # row | col
    gap: str = "0px"
    padding_top: str = "0px"
    padding_right: str = "0px"
    padding_bottom: str = "0px"
    padding_left: str = "0px"
    justify_content: str = "flex-start"
    align_items: str = "flex-start"
    wrap: bool = False


@dataclass
class DesignLayer:
    """A single layer/node in the Penpot design tree."""

    id: str
    name: str
    layer_type: str  # frame | rect | text | image | group | path | vector
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    fill_color: str = ""
    fill_opacity: float = 1.0
    stroke_color: str = ""
    stroke_width: float = 0.0
    border_radius: float = 0.0
    opacity: float = 1.0
    visible: bool = True
    layout: LayoutType = LayoutType.ABSOLUTE
    auto_layout: AutoLayoutConfig | None = None
    constraints: LayoutConstraint = field(default_factory=LayoutConstraint)
    children: list[DesignLayer] = field(default_factory=list)
    text_content: str = ""
    font_size: str = ""
    font_weight: int = 400
    font_color: str = ""
    component_id: str = ""  # Non-empty if this is a component instance
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Component:
    """A reusable Penpot component (akin to a React component)."""

    id: str
    name: str
    file_id: str
    page_id: str
    description: str = ""
    path: str = ""  # Folder path within Penpot, e.g. "Forms/Input"
    layer: DesignLayer | None = None
    svg_content: str = ""
    thumbnail_url: str = ""
    annotations: dict[str, str] = field(default_factory=dict)
    # BANXE-specific: compliance metadata
    is_kyc_component: bool = False
    is_psd2_sca: bool = False
    requires_accessibility_review: bool = False


@dataclass
class PageTree:
    """The full layer tree of a Penpot page."""

    file_id: str
    page_id: str
    page_name: str
    root: DesignLayer | None = None
    components: list[Component] = field(default_factory=list)


# ── Generation Result Models ──────────────────────────────────────────────────


@dataclass
class VisualQAResult:
    """Result from visual QA comparison."""

    component_id: str
    status: QAStatus
    similarity_score: float  # 0.0 - 1.0
    diff_image_path: str = ""
    diff_pixel_count: int = 0
    threshold: float = 0.95
    error_message: str = ""

    @property
    def passed(self) -> bool:
        return self.status == QAStatus.PASS


@dataclass
class GenerationResult:
    """Result of AI-powered code generation."""

    component_id: str
    framework: Framework
    code: str
    mitosis_jsx: str = ""
    qa_result: VisualQAResult | None = None
    tokens_used: int = 0
    latency_ms: int = 0
    model_used: str = ""
    prompt_version: str = "v1"
    error_message: str = ""

    @property
    def success(self) -> bool:
        return bool(self.code) and not self.error_message

    @property
    def qa_passed(self) -> bool:
        if self.qa_result is None:
            return False
        return self.qa_result.passed


@dataclass
class TokenSyncResult:
    """Result of a design token synchronization from Penpot."""

    file_id: str
    tokens_extracted: int
    output_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


# ── MCP Tool Response Models ──────────────────────────────────────────────────


@dataclass
class ComponentListEntry:
    """Lightweight component descriptor for API list responses."""

    id: str
    name: str
    path: str
    file_id: str
    thumbnail_url: str = ""
    is_compliance: bool = False


@dataclass
class DesignPipelineMetrics:
    """Metrics emitted to ClickHouse for Grafana dashboard."""

    component_id: str
    framework: str
    tokens_used: int
    latency_ms: int
    qa_similarity: float
    qa_passed: bool
    model_used: str
    agent_type: str  # orchestrator | compliance_ui | transaction_ui | report_ui | onboarding
    cost_usd: Decimal = Decimal("0")

    def to_clickhouse_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "framework": self.framework,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "qa_similarity": self.qa_similarity,
            "qa_passed": int(self.qa_passed),
            "model_used": self.model_used,
            "agent_type": self.agent_type,
            "cost_usd": str(self.cost_usd),
        }
