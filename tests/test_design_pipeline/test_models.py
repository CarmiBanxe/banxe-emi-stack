"""
tests/test_design_pipeline/test_models.py
IL-D2C-01 — Domain model tests (Component, DesignTokenSet, GenerationResult, etc.)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.design_pipeline.models import (
    ColorToken,
    Component,
    DesignLayer,
    DesignPipelineMetrics,
    DesignTokenSet,
    Framework,
    GenerationResult,
    QAStatus,
    ShadowToken,
    SpacingToken,
    TokenCategory,
    TokenSyncResult,
    TypographyToken,
    VisualQAResult,
)


class TestFrameworkEnum:
    def test_react_value(self) -> None:
        assert Framework.REACT.value == "react"

    def test_vue_value(self) -> None:
        assert Framework.VUE.value == "vue"

    def test_react_native_value(self) -> None:
        assert Framework.REACT_NATIVE.value == "react-native"

    def test_angular_value(self) -> None:
        assert Framework.ANGULAR.value == "angular"

    def test_svelte_value(self) -> None:
        assert Framework.SVELTE.value == "svelte"


class TestColorToken:
    def test_color_token_creation(self) -> None:
        token = ColorToken(name="primary", value="#1A73E8")
        assert token.name == "primary"
        assert token.value == "#1A73E8"

    def test_color_token_default_category(self) -> None:
        token = ColorToken(name="primary", value="#1A73E8")
        assert token.category == TokenCategory.COLOR

    def test_color_token_is_immutable(self) -> None:
        token = ColorToken(name="primary", value="#1A73E8")
        with pytest.raises((AttributeError, TypeError)):
            token.name = "secondary"  # type: ignore[misc]


class TestTypographyToken:
    def test_typography_token_creation(self) -> None:
        token = TypographyToken(
            name="body",
            font_family="Inter",
            font_size="16px",
            font_weight=400,
            line_height=1.5,
        )
        assert token.name == "body"
        assert token.font_size == "16px"

    def test_typography_token_default_letter_spacing(self) -> None:
        token = TypographyToken(
            name="body",
            font_family="Inter",
            font_size="16px",
            font_weight=400,
            line_height=1.5,
        )
        assert token.letter_spacing == "0px"


class TestSpacingToken:
    def test_spacing_token_creation(self) -> None:
        token = SpacingToken(name="md", value="16px")
        assert token.name == "md"
        assert token.value == "16px"


class TestDesignTokenSet:
    def test_empty_token_set(self) -> None:
        ts = DesignTokenSet(file_id="file-001")
        assert ts.file_id == "file-001"
        assert ts.colors == []
        assert ts.typography == []
        assert ts.spacing == []

    def test_to_style_dictionary_format_empty(self) -> None:
        ts = DesignTokenSet(file_id="file-001")
        sd = ts.to_style_dictionary_format()
        assert sd["color"] == {}
        assert sd["spacing"] == {}

    def test_to_style_dictionary_format_with_colors(self) -> None:
        ts = DesignTokenSet(file_id="file-001")
        ts.colors = [ColorToken(name="primary", value="#1A73E8", comment="Brand color")]
        sd = ts.to_style_dictionary_format()
        assert sd["color"]["primary"]["value"] == "#1A73E8"
        assert sd["color"]["primary"]["comment"] == "Brand color"

    def test_to_style_dictionary_format_with_typography(self) -> None:
        ts = DesignTokenSet(file_id="file-001")
        ts.typography = [
            TypographyToken(
                name="heading-1",
                font_family="Inter",
                font_size="32px",
                font_weight=700,
                line_height=1.2,
            )
        ]
        sd = ts.to_style_dictionary_format()
        typo = sd["typography"]["heading-1"]["value"]
        assert typo["fontFamily"] == "Inter"
        assert typo["fontSize"] == "32px"
        assert typo["fontWeight"] == 700

    def test_to_style_dictionary_format_with_spacing(self) -> None:
        ts = DesignTokenSet(file_id="file-001")
        ts.spacing = [
            SpacingToken(name="md", value="16px"),
            SpacingToken(name="lg", value="24px"),
        ]
        sd = ts.to_style_dictionary_format()
        assert sd["spacing"]["md"]["value"] == "16px"
        assert sd["spacing"]["lg"]["value"] == "24px"

    def test_to_style_dictionary_format_shadows(self) -> None:
        ts = DesignTokenSet(file_id="file-001")
        ts.shadows = [ShadowToken(name="sm", value="0 1px 3px rgba(0,0,0,0.12)")]
        sd = ts.to_style_dictionary_format()
        assert sd["shadow"]["sm"]["value"] == "0 1px 3px rgba(0,0,0,0.12)"


class TestDesignLayer:
    def test_design_layer_defaults(self) -> None:
        layer = DesignLayer(id="l1", name="Frame", layer_type="frame")
        assert layer.x == 0.0
        assert layer.y == 0.0
        assert layer.visible is True
        assert layer.opacity == 1.0

    def test_design_layer_children_default_empty(self) -> None:
        layer = DesignLayer(id="l1", name="Frame", layer_type="frame")
        assert layer.children == []


class TestComponent:
    def test_component_creation(self) -> None:
        comp = Component(
            id="comp-001",
            name="PrimaryButton",
            file_id="file-001",
            page_id="page-001",
        )
        assert comp.id == "comp-001"
        assert comp.name == "PrimaryButton"
        assert comp.is_kyc_component is False
        assert comp.is_psd2_sca is False


class TestVisualQAResult:
    def test_passed_property_true(self) -> None:
        result = VisualQAResult(
            component_id="comp-001",
            status=QAStatus.PASS,
            similarity_score=0.98,
        )
        assert result.passed is True

    def test_passed_property_false(self) -> None:
        result = VisualQAResult(
            component_id="comp-001",
            status=QAStatus.FAIL,
            similarity_score=0.80,
        )
        assert result.passed is False

    def test_pending_not_passed(self) -> None:
        result = VisualQAResult(
            component_id="comp-001",
            status=QAStatus.PENDING,
            similarity_score=0.0,
        )
        assert result.passed is False

    def test_skipped_not_passed(self) -> None:
        result = VisualQAResult(
            component_id="comp-001",
            status=QAStatus.SKIPPED,
            similarity_score=0.0,
        )
        assert result.passed is False


class TestGenerationResult:
    def test_success_when_code_present(self) -> None:
        result = GenerationResult(
            component_id="comp-001",
            framework=Framework.REACT,
            code="const App = () => <div/>;",
        )
        assert result.success is True

    def test_success_false_when_error(self) -> None:
        result = GenerationResult(
            component_id="comp-001",
            framework=Framework.REACT,
            code="",
            error_message="LLM failed",
        )
        assert result.success is False

    def test_success_false_when_no_code(self) -> None:
        result = GenerationResult(
            component_id="comp-001",
            framework=Framework.REACT,
            code="",
        )
        assert result.success is False

    def test_qa_passed_none_qa(self) -> None:
        result = GenerationResult(
            component_id="comp-001",
            framework=Framework.REACT,
            code="some code",
        )
        assert result.qa_passed is False

    def test_qa_passed_with_passing_result(self) -> None:
        qa = VisualQAResult(
            component_id="comp-001",
            status=QAStatus.PASS,
            similarity_score=0.98,
        )
        result = GenerationResult(
            component_id="comp-001",
            framework=Framework.REACT,
            code="some code",
            qa_result=qa,
        )
        assert result.qa_passed is True


class TestTokenSyncResult:
    def test_success_when_no_errors(self) -> None:
        result = TokenSyncResult(
            file_id="file-001",
            tokens_extracted=10,
            output_files=["tokens.css"],
        )
        assert result.success is True

    def test_failure_when_errors(self) -> None:
        result = TokenSyncResult(
            file_id="file-001",
            tokens_extracted=0,
            errors=["CLI not found"],
        )
        assert result.success is False


class TestDesignPipelineMetrics:
    def test_metrics_no_float_for_cost(self) -> None:
        """Financial invariant: cost_usd must be Decimal, not float."""
        m = DesignPipelineMetrics(
            component_id="comp",
            framework="react",
            tokens_used=1000,
            latency_ms=500,
            qa_similarity=0.97,
            qa_passed=True,
            model_used="qwen2.5-coder:7b",
            agent_type="orchestrator",
            cost_usd=Decimal("0.001"),
        )
        assert isinstance(m.cost_usd, Decimal)
        assert m.cost_usd == Decimal("0.001")

    def test_to_clickhouse_dict_structure(self) -> None:
        m = DesignPipelineMetrics(
            component_id="comp-001",
            framework="react",
            tokens_used=500,
            latency_ms=200,
            qa_similarity=0.98,
            qa_passed=True,
            model_used="in-memory",
            agent_type="orchestrator",
        )
        d = m.to_clickhouse_dict()
        assert d["component_id"] == "comp-001"
        assert d["framework"] == "react"
        assert d["qa_passed"] == 1  # int, not bool
        assert isinstance(d["cost_usd"], str)  # Decimal as string

    def test_to_clickhouse_dict_qa_failed_is_zero(self) -> None:
        m = DesignPipelineMetrics(
            component_id="comp",
            framework="vue",
            tokens_used=0,
            latency_ms=0,
            qa_similarity=0.0,
            qa_passed=False,
            model_used="in-memory",
            agent_type="compliance_ui",
        )
        d = m.to_clickhouse_dict()
        assert d["qa_passed"] == 0
