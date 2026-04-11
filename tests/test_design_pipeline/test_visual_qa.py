"""
tests/test_design_pipeline/test_visual_qa.py
IL-D2C-01 — Visual QA screenshot comparison tests
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.design_pipeline.models import QAStatus
from services.design_pipeline.visual_qa import (
    BackstopConfigGenerator,
    BackstopScenario,
    InMemoryVisualQA,
    PlaywrightVisualQA,
    VisualQAError,
)


class TestInMemoryVisualQA:
    """Tests use InMemoryVisualQA — no Playwright dependency."""

    @pytest.mark.asyncio
    async def test_compare_returns_result(self) -> None:
        qa = InMemoryVisualQA(similarity=0.97)
        result = await qa.compare(
            component_id="comp-001",
            rendered_html="<div>test</div>",
            reference_svg="<svg><rect/></svg>",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_compare_high_similarity_passes(self) -> None:
        qa = InMemoryVisualQA(similarity=0.97)
        result = await qa.compare("comp-001", "<div>test</div>", "<svg/>", threshold=0.95)
        assert result.status == QAStatus.PASS
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_compare_low_similarity_fails(self) -> None:
        qa = InMemoryVisualQA(similarity=0.80)
        result = await qa.compare("comp-001", "<div>test</div>", "<svg/>", threshold=0.95)
        assert result.status == QAStatus.FAIL
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_compare_returns_correct_score(self) -> None:
        qa = InMemoryVisualQA(similarity=0.92)
        result = await qa.compare("comp-001", "<div>test</div>", "<svg/>")
        assert abs(result.similarity_score - 0.92) < 0.001

    @pytest.mark.asyncio
    async def test_compare_at_exact_threshold_passes(self) -> None:
        qa = InMemoryVisualQA(similarity=0.95)
        result = await qa.compare("comp-001", "<div/>", "<svg/>", threshold=0.95)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_compare_just_below_threshold_fails(self) -> None:
        qa = InMemoryVisualQA(similarity=0.949)
        result = await qa.compare("comp-001", "<div/>", "<svg/>", threshold=0.95)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_compare_component_id_in_result(self) -> None:
        qa = InMemoryVisualQA()
        result = await qa.compare("my-component", "<div/>", "<svg/>")
        assert result.component_id == "my-component"

    @pytest.mark.asyncio
    async def test_compare_threshold_in_result(self) -> None:
        qa = InMemoryVisualQA()
        result = await qa.compare("comp", "<div/>", "<svg/>", threshold=0.85)
        assert result.threshold == 0.85

    @pytest.mark.asyncio
    async def test_compare_pass_has_zero_diff_pixels(self) -> None:
        qa = InMemoryVisualQA(similarity=0.99)
        result = await qa.compare("comp", "<div/>", "<svg/>", threshold=0.95)
        assert result.diff_pixel_count == 0

    @pytest.mark.asyncio
    async def test_compare_fail_has_nonzero_diff_pixels(self) -> None:
        qa = InMemoryVisualQA(similarity=0.50)
        result = await qa.compare("comp", "<div/>", "<svg/>", threshold=0.95)
        assert result.diff_pixel_count > 0

    @pytest.mark.asyncio
    async def test_compare_custom_threshold_0_always_passes(self) -> None:
        qa = InMemoryVisualQA(similarity=0.0)
        result = await qa.compare("comp", "<div/>", "<svg/>", threshold=0.0)
        assert result.passed is True


class TestPlaywrightVisualQAHelpers:
    """Test static helpers without launching a browser."""

    def test_wrap_component_in_html_contains_doctype(self) -> None:
        html = PlaywrightVisualQA._wrap_component_in_html("// some code")
        assert "<!DOCTYPE html>" in html

    def test_wrap_component_in_html_contains_token_vars(self) -> None:
        html = PlaywrightVisualQA._wrap_component_in_html("// code")
        assert "--banxe-color-primary" in html

    def test_wrap_component_in_html_contains_root_div(self) -> None:
        html = PlaywrightVisualQA._wrap_component_in_html("// code")
        assert 'id="root"' in html

    def test_compare_images_pillow_fallback(self) -> None:
        """_compare_images handles invalid bytes gracefully — returns floats/ints."""
        # Invalid PNG bytes trigger the exception handler
        bad_bytes = b"not a png"
        similarity, diff = PlaywrightVisualQA._compare_images(bad_bytes, bad_bytes)
        assert 0.0 <= similarity <= 1.0
        assert isinstance(diff, int)

    def test_svg_to_png_empty_svg_returns_bytes(self) -> None:
        result = PlaywrightVisualQA._svg_to_png("")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_svg_to_png_with_svg_content(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
        result = PlaywrightVisualQA._svg_to_png(svg)
        assert isinstance(result, bytes)


class TestVisualQAError:
    def test_error_message(self) -> None:
        err = VisualQAError("comparison failed", context={"component": "btn"})
        assert "comparison failed" in str(err)
        assert err.context["component"] == "btn"

    def test_error_empty_context(self) -> None:
        err = VisualQAError("test")
        assert err.context == {}


class TestBackstopConfigGenerator:
    def test_generate_returns_dict(self) -> None:
        gen = BackstopConfigGenerator()
        config = gen.generate(["Button", "Input"])
        assert isinstance(config, dict)

    def test_generate_has_scenarios(self) -> None:
        gen = BackstopConfigGenerator()
        config = gen.generate(["Button", "Card"])
        assert "scenarios" in config
        assert len(config["scenarios"]) == 2

    def test_generate_has_viewports(self) -> None:
        gen = BackstopConfigGenerator()
        config = gen.generate(["Button"])
        assert "viewports" in config
        assert len(config["viewports"]) >= 1

    def test_generate_has_engine_playwright(self) -> None:
        gen = BackstopConfigGenerator()
        config = gen.generate(["Button"])
        assert config["engine"] == "playwright"

    def test_generate_scenario_has_label(self) -> None:
        gen = BackstopConfigGenerator()
        config = gen.generate(["MyButton"])
        assert config["scenarios"][0]["label"] == "MyButton"

    def test_generate_storybook_url_in_scenario(self) -> None:
        gen = BackstopConfigGenerator(storybook_url="http://localhost:6007")
        config = gen.generate(["Button"])
        url = config["scenarios"][0]["url"]
        assert "localhost:6007" in url

    def test_write_config_creates_file(self, tmp_path: Path) -> None:
        gen = BackstopConfigGenerator()
        output_path = str(tmp_path / "backstop.json")
        gen.write_config(["Button", "Input"], output_path)
        assert Path(output_path).exists()
        with open(output_path) as f:
            data = json.load(f)
        assert "scenarios" in data

    def test_backstop_scenario_to_dict(self) -> None:
        scenario = BackstopScenario(label="Test", url="http://localhost:6006/iframe.html?id=test")
        d = scenario.to_dict()
        assert d["label"] == "Test"
        assert "selectors" in d

    def test_generate_empty_components(self) -> None:
        gen = BackstopConfigGenerator()
        config = gen.generate([])
        assert config["scenarios"] == []
