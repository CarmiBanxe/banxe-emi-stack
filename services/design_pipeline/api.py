"""
services/design_pipeline/api.py — FastAPI Router for Design-to-Code Pipeline
IL-D2C-01 | BANXE EMI AI Bank

Endpoints:
  POST /design/generate-component  — Generate UI component from Penpot design
  POST /design/generate-page       — Generate all components on a page
  POST /design/sync-tokens         — Sync tokens from Penpot to codebase
  POST /design/visual-compare      — Compare implementation vs design
  GET  /design/components/{file_id} — List available Penpot components
  GET  /design/tokens/{file_id}    — Get current design tokens for a file

FCA/GDPR: no PII in request/response bodies.
EU AI Act Art.52: all generated code is labelled as AI-generated.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.design_pipeline.code_generator import InMemoryCodeGenerator, MitosisGenerator
from services.design_pipeline.models import (
    Framework,
    GenerationResult,
    TokenSyncResult,
    VisualQAResult,
)
from services.design_pipeline.orchestrator import DesignToCodeOrchestrator, InMemoryLLM, OllamaLLM
from services.design_pipeline.penpot_client import InMemoryPenpotClient, PenpotMCPClient
from services.design_pipeline.token_extractor import TokenExtractor
from services.design_pipeline.visual_qa import InMemoryVisualQA, PlaywrightVisualQA

logger = logging.getLogger("banxe.design_pipeline.api")

router = APIRouter(prefix="/design", tags=["design-pipeline"])


# ── Dependency injection helpers ──────────────────────────────────────────────


def _get_penpot_client():
    """Return a Penpot client based on environment configuration."""
    base_url = os.environ.get("PENPOT_BASE_URL", "")
    token = os.environ.get("PENPOT_TOKEN", "")
    if base_url and token:
        return PenpotMCPClient(base_url=base_url, token=token)
    logger.warning("PENPOT_BASE_URL/PENPOT_TOKEN not set — using InMemory Penpot client")
    return InMemoryPenpotClient()


def _get_llm():
    """Return LLM backend based on environment."""
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "")
    if ollama_url:
        return OllamaLLM(
            base_url=ollama_url,
            model=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        )
    return InMemoryLLM()


def _get_orchestrator() -> DesignToCodeOrchestrator:
    penpot = _get_penpot_client()
    llm = _get_llm()
    generator = (
        MitosisGenerator()
        if os.environ.get("MITOSIS_ENABLED", "false").lower() == "true"
        else InMemoryCodeGenerator()
    )
    visual_qa = (
        PlaywrightVisualQA()
        if os.environ.get("VISUAL_QA_ENABLED", "false").lower() == "true"
        else InMemoryVisualQA()
    )
    return DesignToCodeOrchestrator(
        penpot_client=penpot,
        llm=llm,
        code_generator=generator,
        visual_qa=visual_qa,
        token_extractor=TokenExtractor(penpot),
    )


# ── Request / Response schemas ────────────────────────────────────────────────


class GenerateComponentRequest(BaseModel):
    file_id: str = Field(..., description="Penpot file UUID")
    component_id: str = Field(..., description="Penpot component UUID")
    framework: Framework = Field(Framework.REACT, description="Target framework")
    run_visual_qa: bool = Field(True, description="Run screenshot comparison")


class GeneratePageRequest(BaseModel):
    file_id: str = Field(..., description="Penpot file UUID")
    page_id: str = Field(..., description="Penpot page UUID")
    framework: Framework = Field(Framework.REACT, description="Target framework")


class SyncTokensRequest(BaseModel):
    file_id: str = Field(..., description="Penpot file UUID to sync tokens from")


class VisualCompareRequest(BaseModel):
    component_id: str = Field(..., description="Component ID")
    rendered_html: str = Field(..., description="Rendered HTML/component code")
    reference_svg: str = Field(..., description="Reference SVG from Penpot")
    threshold: float = Field(0.95, ge=0.0, le=1.0, description="Similarity threshold")


class GenerateComponentResponse(BaseModel):
    component_id: str
    framework: str
    code: str
    mitosis_jsx: str = ""
    qa_passed: bool = False
    qa_similarity: float = 0.0
    tokens_used: int = 0
    latency_ms: int = 0
    model_used: str = ""
    success: bool = True
    error_message: str = ""

    @classmethod
    def from_result(cls, result: GenerationResult) -> GenerateComponentResponse:
        return cls(
            component_id=result.component_id,
            framework=result.framework.value,
            code=result.code,
            mitosis_jsx=result.mitosis_jsx,
            qa_passed=result.qa_passed,
            qa_similarity=result.qa_result.similarity_score if result.qa_result else 0.0,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
            model_used=result.model_used,
            success=result.success,
            error_message=result.error_message,
        )


class TokenSyncResponse(BaseModel):
    file_id: str
    tokens_extracted: int
    output_files: list[str]
    errors: list[str]
    success: bool

    @classmethod
    def from_result(cls, result: TokenSyncResult) -> TokenSyncResponse:
        return cls(
            file_id=result.file_id,
            tokens_extracted=result.tokens_extracted,
            output_files=result.output_files,
            errors=result.errors,
            success=result.success,
        )


class VisualCompareResponse(BaseModel):
    component_id: str
    status: str
    similarity_score: float
    diff_image_path: str = ""
    diff_pixel_count: int = 0
    threshold: float
    passed: bool

    @classmethod
    def from_result(cls, result: VisualQAResult) -> VisualCompareResponse:
        return cls(
            component_id=result.component_id,
            status=result.status.value,
            similarity_score=result.similarity_score,
            diff_image_path=result.diff_image_path,
            diff_pixel_count=result.diff_pixel_count,
            threshold=result.threshold,
            passed=result.passed,
        )


class ComponentListResponse(BaseModel):
    file_id: str
    count: int
    components: list[dict[str, Any]]


class TokensResponse(BaseModel):
    file_id: str
    color_count: int
    typography_count: int
    spacing_count: int
    style_dictionary: dict[str, Any]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/generate-component", response_model=GenerateComponentResponse)
async def generate_component(body: GenerateComponentRequest) -> GenerateComponentResponse:
    """
    Generate a UI component from a Penpot design.

    Runs the full pipeline: Penpot context → LLM → Mitosis compile → Visual QA.
    AI-generated code is labelled per EU AI Act Art.52.
    """
    orchestrator = _get_orchestrator()
    try:
        result = await orchestrator.generate_component(
            file_id=body.file_id,
            component_id=body.component_id,
            framework=body.framework,
            run_visual_qa=body.run_visual_qa,
        )
        await orchestrator.emit_metrics(result, agent_type="orchestrator")
        return GenerateComponentResponse.from_result(result)
    except Exception as exc:
        logger.error("generate_component failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate-page", response_model=list[GenerateComponentResponse])
async def generate_page(body: GeneratePageRequest) -> list[GenerateComponentResponse]:
    """Generate code for all components on a Penpot page."""
    orchestrator = _get_orchestrator()
    try:
        results = await orchestrator.generate_page(
            file_id=body.file_id,
            page_id=body.page_id,
            framework=body.framework,
        )
        return [GenerateComponentResponse.from_result(r) for r in results]
    except Exception as exc:
        logger.error("generate_page failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sync-tokens", response_model=TokenSyncResponse)
async def sync_tokens(body: SyncTokensRequest) -> TokenSyncResponse:
    """
    Sync design tokens from Penpot to codebase.

    Runs: Penpot → banxe-tokens.json → Style Dictionary → CSS/Tailwind/RN outputs.
    """
    orchestrator = _get_orchestrator()
    try:
        result = await orchestrator.sync_tokens(file_id=body.file_id)
        return TokenSyncResponse.from_result(result)
    except Exception as exc:
        logger.error("sync_tokens failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/visual-compare", response_model=VisualCompareResponse)
async def visual_compare(body: VisualCompareRequest) -> VisualCompareResponse:
    """
    Compare a rendered component against its Penpot reference design.

    Returns similarity score and diff image path if below threshold.
    """
    qa = (
        PlaywrightVisualQA(threshold=body.threshold)
        if os.environ.get("VISUAL_QA_ENABLED", "false").lower() == "true"
        else InMemoryVisualQA()
    )
    try:
        result = await qa.compare(
            component_id=body.component_id,
            rendered_html=body.rendered_html,
            reference_svg=body.reference_svg,
            threshold=body.threshold,
        )
        return VisualCompareResponse.from_result(result)
    except Exception as exc:
        logger.error("visual_compare failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/components/{file_id}", response_model=ComponentListResponse)
async def list_design_components(file_id: str) -> ComponentListResponse:
    """List all available Penpot components for a file."""
    penpot = _get_penpot_client()
    try:
        components = await penpot.list_components_flat(file_id)
        return ComponentListResponse(
            file_id=file_id,
            count=len(components),
            components=[
                {
                    "id": c.id,
                    "name": c.name,
                    "path": c.path,
                    "is_compliance": c.is_compliance,
                }
                for c in components
            ],
        )
    except Exception as exc:
        logger.error("list_design_components failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tokens/{file_id}", response_model=TokensResponse)
async def get_design_tokens(file_id: str) -> TokensResponse:
    """Get design tokens for a Penpot file in Style Dictionary format."""
    penpot = _get_penpot_client()
    try:
        token_set = await penpot.get_design_tokens(file_id)
        return TokensResponse(
            file_id=file_id,
            color_count=len(token_set.colors),
            typography_count=len(token_set.typography),
            spacing_count=len(token_set.spacing),
            style_dictionary=token_set.to_style_dictionary_format(),
        )
    except Exception as exc:
        logger.error("get_design_tokens failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
