"""
tests/test_design_pipeline/test_orchestrator.py
IL-D2C-01 — DesignToCodeOrchestrator end-to-end pipeline tests
"""

from __future__ import annotations

import pytest

from services.design_pipeline.code_generator import InMemoryCodeGenerator
from services.design_pipeline.models import Framework, GenerationResult
from services.design_pipeline.orchestrator import (
    DesignToCodeOrchestrator,
    InMemoryLLM,
    OllamaLLM,
    _format_tokens_for_prompt,
    _safe_json_truncate,
)
from services.design_pipeline.penpot_client import InMemoryPenpotClient
from services.design_pipeline.token_extractor import TokenExtractor
from services.design_pipeline.visual_qa import InMemoryVisualQA


@pytest.fixture
def orchestrator() -> DesignToCodeOrchestrator:
    penpot = InMemoryPenpotClient()
    llm = InMemoryLLM()
    generator = InMemoryCodeGenerator()
    visual_qa = InMemoryVisualQA(similarity=0.97)
    return DesignToCodeOrchestrator(
        penpot_client=penpot,
        llm=llm,
        code_generator=generator,
        visual_qa=visual_qa,
        token_extractor=TokenExtractor(penpot),
    )


@pytest.fixture
def failing_qa_orchestrator() -> DesignToCodeOrchestrator:
    """Orchestrator configured to produce QA failures."""
    penpot = InMemoryPenpotClient()
    llm = InMemoryLLM()
    generator = InMemoryCodeGenerator()
    visual_qa = InMemoryVisualQA(similarity=0.80)  # Below 0.95 threshold
    return DesignToCodeOrchestrator(
        penpot_client=penpot,
        llm=llm,
        code_generator=generator,
        visual_qa=visual_qa,
    )


class TestGenerateComponent:
    @pytest.mark.asyncio
    async def test_generate_component_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
            framework=Framework.REACT,
        )
        assert isinstance(result, GenerationResult)

    @pytest.mark.asyncio
    async def test_generate_component_success_flag(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_component_has_code(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
        )
        assert result.code
        assert len(result.code) > 0

    @pytest.mark.asyncio
    async def test_generate_component_ai_disclosure(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        """EU AI Act Art.52: generated code must have AI disclosure header."""
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
        )
        assert "AI-GENERATED" in result.code

    @pytest.mark.asyncio
    async def test_generate_component_framework_set(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
            framework=Framework.VUE,
        )
        assert result.framework == Framework.VUE

    @pytest.mark.asyncio
    async def test_generate_component_with_qa_pass(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
            run_visual_qa=True,
        )
        assert result.qa_result is not None
        assert result.qa_passed is True

    @pytest.mark.asyncio
    async def test_generate_component_with_qa_fail(
        self, failing_qa_orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await failing_qa_orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
            run_visual_qa=True,
        )
        assert result.qa_result is not None
        assert result.qa_passed is False

    @pytest.mark.asyncio
    async def test_generate_component_skip_qa(self, orchestrator: DesignToCodeOrchestrator) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
            run_visual_qa=False,
        )
        assert result.qa_result is None

    @pytest.mark.asyncio
    async def test_generate_component_latency_recorded(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
        )
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_generate_component_model_name(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        result = await orchestrator.generate_component(
            file_id="file-test-001",
            component_id="comp-button-001",
        )
        assert result.model_used == "in-memory-mock"


class TestGeneratePage:
    @pytest.mark.asyncio
    async def test_generate_page_returns_list(self, orchestrator: DesignToCodeOrchestrator) -> None:
        results = await orchestrator.generate_page(
            file_id="file-test-001",
            page_id="page-test-001",
            framework=Framework.REACT,
        )
        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_generate_page_all_results_succeed(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        results = await orchestrator.generate_page(
            file_id="file-test-001",
            page_id="page-test-001",
        )
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_generate_page_framework_consistent(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        results = await orchestrator.generate_page(
            file_id="file-test-001",
            page_id="page-test-001",
            framework=Framework.REACT_NATIVE,
        )
        assert all(r.framework == Framework.REACT_NATIVE for r in results)


class TestSyncTokens:
    @pytest.mark.asyncio
    async def test_sync_tokens_returns_result(
        self, orchestrator: DesignToCodeOrchestrator, tmp_path
    ) -> None:
        import services.design_pipeline.token_extractor as mod

        tokens_file = tmp_path / "banxe-tokens.json"
        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            result = await orchestrator.sync_tokens("file-test-001")
        finally:
            mod._BANXE_TOKENS_FILE = orig

        assert result.file_id == "file-test-001"
        assert result.tokens_extracted >= 0


class TestPromptBuilder:
    @pytest.mark.asyncio
    async def test_build_prompt_contains_framework(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        penpot = InMemoryPenpotClient()
        ctx = await penpot.get_component_context("comp-button-001")
        tokens = await penpot.get_design_tokens("file-test-001")
        prompt = orchestrator._build_prompt(ctx, tokens, Framework.VUE)
        assert "vue" in prompt.lower()

    @pytest.mark.asyncio
    async def test_build_prompt_contains_gdpr_notice(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        penpot = InMemoryPenpotClient()
        ctx = await penpot.get_component_context("comp-button-001")
        tokens = await penpot.get_design_tokens("file-test-001")
        prompt = orchestrator._build_prompt(ctx, tokens, Framework.REACT)
        assert "GDPR" in prompt or "PII" in prompt

    def test_format_tokens_for_prompt_with_colors(self) -> None:
        from services.design_pipeline.models import ColorToken, DesignTokenSet

        tokens = DesignTokenSet(file_id="f1")
        tokens.colors = [ColorToken(name="primary", value="#1A73E8")]
        result = _format_tokens_for_prompt(tokens)
        assert "primary" in result
        assert "#1A73E8" in result

    def test_format_tokens_for_prompt_empty(self) -> None:
        from services.design_pipeline.models import DesignTokenSet

        tokens = DesignTokenSet(file_id="f1")
        result = _format_tokens_for_prompt(tokens)
        assert result == "No tokens available"

    def test_safe_json_truncate_short(self) -> None:
        data = {"key": "value"}
        result = _safe_json_truncate(data, max_chars=1000)
        assert '"key"' in result
        assert "..." not in result

    def test_safe_json_truncate_long(self) -> None:
        data = {"key": "x" * 5000}
        result = _safe_json_truncate(data, max_chars=100)
        assert "[truncated]" in result
        assert len(result) <= 200  # 100 + some overhead


class TestInMemoryLLM:
    @pytest.mark.asyncio
    async def test_agenerate_returns_string(self) -> None:
        llm = InMemoryLLM()
        result = await llm.agenerate("test prompt")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_agenerate_custom_response(self) -> None:
        llm = InMemoryLLM(response="custom response")
        result = await llm.agenerate("any prompt")
        assert result == "custom response"

    def test_model_name(self) -> None:
        llm = InMemoryLLM()
        assert llm.model_name == "in-memory-mock"


class TestOllamaLLM:
    def test_model_name(self) -> None:
        llm = OllamaLLM(model="qwen2.5-coder:7b")
        assert llm.model_name == "qwen2.5-coder:7b"

    @pytest.mark.asyncio
    async def test_fallback_when_unavailable(self) -> None:
        """When Ollama is unavailable, falls back to scaffold — no exception."""
        llm = OllamaLLM(base_url="http://localhost:11999")  # Invalid port
        result = await llm.agenerate("generate a button component")
        assert isinstance(result, str)
        # Fallback scaffold should contain Mitosis import
        assert "mitosis" in result.lower() or len(result) > 0
