"""
tests/test_design_pipeline/test_agents.py
IL-D2C-01 — BANXE UI Agents tests (ComplianceUI, Transaction, Report, Onboarding)
"""

from __future__ import annotations

import pytest

from services.design_pipeline.agents.compliance_ui_agent import (
    ComplianceFormField,
    ComplianceFormSpec,
    ComplianceUIAgent,
)
from services.design_pipeline.agents.onboarding_agent import OnboardingAgent, OnboardingStep
from services.design_pipeline.agents.report_ui_agent import ReportUIAgent
from services.design_pipeline.agents.transaction_ui_agent import TransactionUIAgent
from services.design_pipeline.code_generator import InMemoryCodeGenerator
from services.design_pipeline.models import Framework, GenerationResult
from services.design_pipeline.orchestrator import DesignToCodeOrchestrator, InMemoryLLM
from services.design_pipeline.penpot_client import InMemoryPenpotClient
from services.design_pipeline.token_extractor import TokenExtractor
from services.design_pipeline.visual_qa import InMemoryVisualQA


@pytest.fixture
def orchestrator() -> DesignToCodeOrchestrator:
    penpot = InMemoryPenpotClient()
    return DesignToCodeOrchestrator(
        penpot_client=penpot,
        llm=InMemoryLLM(),
        code_generator=InMemoryCodeGenerator(),
        visual_qa=InMemoryVisualQA(),
        token_extractor=TokenExtractor(penpot),
    )


# ── ComplianceUIAgent ─────────────────────────────────────────────────────────


class TestComplianceUIAgent:
    @pytest.mark.asyncio
    async def test_generate_kyc_form_individual_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_kyc_form("kyc_individual")
        assert isinstance(result, GenerationResult)

    @pytest.mark.asyncio
    async def test_generate_kyc_form_individual_success(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_kyc_form("kyc_individual")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_kyc_form_corporate_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_kyc_form("kyc_corporate")
        assert isinstance(result, GenerationResult)

    @pytest.mark.asyncio
    async def test_generate_kyc_component_id_individual(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_kyc_form("kyc_individual")
        assert "kyc_individual" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_kyc_component_id_corporate(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_kyc_form("kyc_corporate")
        assert "kyc_corporate" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_aml_declaration_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_aml_declaration()
        assert isinstance(result, GenerationResult)
        assert "aml_declaration" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_consent_screen_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_consent_screen()
        assert isinstance(result, GenerationResult)
        assert "gdpr_consent" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_kyc_with_vue_framework(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ComplianceUIAgent(orchestrator)
        result = await agent.generate_kyc_form("kyc_individual", framework=Framework.VUE)
        assert result.framework == Framework.VUE

    def test_get_kyc_spec_individual_has_name_field(self) -> None:
        spec = ComplianceUIAgent._get_kyc_spec("kyc_individual")
        field_names = [f.name for f in spec.fields]
        assert "full_name" in field_names

    def test_get_kyc_spec_corporate_has_company_name(self) -> None:
        spec = ComplianceUIAgent._get_kyc_spec("kyc_corporate")
        field_names = [f.name for f in spec.fields]
        assert "company_name" in field_names

    def test_get_kyc_spec_individual_has_regulatory_basis(self) -> None:
        spec = ComplianceUIAgent._get_kyc_spec("kyc_individual")
        assert len(spec.regulatory_basis) > 0
        assert any("MLR" in r for r in spec.regulatory_basis)

    def test_compliance_form_field_defaults(self) -> None:
        field = ComplianceFormField(name="test", label="Test")
        assert field.required is True
        assert field.input_type == "text"

    def test_build_compliance_prompt_contains_form_type(self) -> None:
        spec = ComplianceFormSpec(
            form_type="test_form",
            title="Test Form",
            fields=[ComplianceFormField(name="f1", label="Field 1")],
            compliance_notices=["Notice 1"],
            regulatory_basis=["MLR 2017"],
        )
        prompt = ComplianceUIAgent._build_compliance_prompt(spec, Framework.REACT)
        assert "test_form" in prompt
        assert "MLR 2017" in prompt


# ── TransactionUIAgent ────────────────────────────────────────────────────────


class TestTransactionUIAgent:
    @pytest.mark.asyncio
    async def test_generate_payment_initiation_fps(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator)
        result = await agent.generate_payment_initiation(rail="fps")
        assert isinstance(result, GenerationResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_payment_initiation_sepa(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator)
        result = await agent.generate_payment_initiation(rail="sepa_ct")
        assert isinstance(result, GenerationResult)

    @pytest.mark.asyncio
    async def test_generate_payment_initiation_component_id(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator)
        result = await agent.generate_payment_initiation(rail="fps")
        assert "payment_initiation" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_sca_challenge_totp(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator)
        result = await agent.generate_sca_challenge(method="totp")
        assert isinstance(result, GenerationResult)
        assert "sca_challenge" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_payment_confirmation_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator)
        result = await agent.generate_payment_confirmation()
        assert isinstance(result, GenerationResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_payment_receipt_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator)
        result = await agent.generate_payment_receipt()
        assert isinstance(result, GenerationResult)

    @pytest.mark.asyncio
    async def test_transaction_agent_with_rn_framework(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = TransactionUIAgent(orchestrator, default_framework=Framework.REACT_NATIVE)
        result = await agent.generate_payment_initiation()
        assert result.framework == Framework.REACT_NATIVE


# ── ReportUIAgent ─────────────────────────────────────────────────────────────


class TestReportUIAgent:
    @pytest.mark.asyncio
    async def test_generate_fin060_view_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ReportUIAgent(orchestrator)
        result = await agent.generate_fin060_view()
        assert isinstance(result, GenerationResult)
        assert "fin060_view" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_sar_review_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ReportUIAgent(orchestrator)
        result = await agent.generate_sar_review_screen()
        assert isinstance(result, GenerationResult)
        assert "sar_review" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_recon_dashboard_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ReportUIAgent(orchestrator)
        result = await agent.generate_recon_dashboard()
        assert isinstance(result, GenerationResult)
        assert "recon_dashboard" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_audit_trail_viewer_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = ReportUIAgent(orchestrator)
        result = await agent.generate_audit_trail_viewer()
        assert isinstance(result, GenerationResult)
        assert "audit_trail_viewer" in result.component_id

    @pytest.mark.asyncio
    async def test_report_agent_success_flag(self, orchestrator: DesignToCodeOrchestrator) -> None:
        agent = ReportUIAgent(orchestrator)
        result = await agent.generate_fin060_view()
        assert result.success is True


# ── OnboardingAgent ───────────────────────────────────────────────────────────


class TestOnboardingAgent:
    @pytest.mark.asyncio
    async def test_generate_welcome_screen_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator)
        result = await agent.generate_welcome_screen()
        assert isinstance(result, GenerationResult)
        assert "welcome" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_personal_details_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator)
        result = await agent.generate_personal_details_screen()
        assert isinstance(result, GenerationResult)
        assert "personal_details" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_document_upload_passport(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator)
        result = await agent.generate_document_upload_screen(document_type="passport")
        assert isinstance(result, GenerationResult)
        assert "passport" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_submitted_screen_returns_result(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator)
        result = await agent.generate_submitted_screen()
        assert isinstance(result, GenerationResult)
        assert "submitted" in result.component_id

    @pytest.mark.asyncio
    async def test_generate_full_flow_returns_list(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator)
        screens = await agent.generate_full_flow()
        assert isinstance(screens, list)
        assert len(screens) >= 4

    @pytest.mark.asyncio
    async def test_generate_full_flow_all_succeed(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator)
        screens = await agent.generate_full_flow()
        assert all(s.success for s in screens)

    @pytest.mark.asyncio
    async def test_onboarding_custom_total_steps(
        self, orchestrator: DesignToCodeOrchestrator
    ) -> None:
        agent = OnboardingAgent(orchestrator, total_steps=10)
        assert agent._total_steps == 10

    def test_build_step_prompt_contains_step_info(self) -> None:
        step = OnboardingStep(
            step_id="test",
            title="Test Step",
            description="Test description",
            step_number=2,
            total_steps=7,
        )
        prompt = OnboardingAgent._build_step_prompt(step, "", Framework.REACT)
        assert "2" in prompt
        assert "7" in prompt
        assert "Test Step" in prompt
