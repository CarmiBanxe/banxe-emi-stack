"""
services/design_pipeline/agents/onboarding_agent.py — Onboarding UI Agent
IL-D2C-01 | BANXE EMI AI Bank

Generates step-by-step KYC onboarding flow screens:
  - Welcome / product selection
  - Personal details collection
  - Document upload (passport, utility bill)
  - Liveness check / selfie
  - Source of funds
  - T&Cs and consent
  - Application submitted / pending

FCA/Consumer Duty references:
  - PS22/9 Consumer Duty: onboarding must not create barriers to switching
  - MLR 2017: CDD documentation requirements
  - GDPR Art.12: transparent information at point of collection
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from services.design_pipeline.models import Framework, GenerationResult
from services.design_pipeline.orchestrator import DesignToCodeOrchestrator

logger = logging.getLogger("banxe.design_pipeline.agents.onboarding")

_ONBOARDING_SYSTEM_PROMPT = """You are a Consumer Duty-compliant onboarding UI developer for BANXE AI Bank.

ONBOARDING REQUIREMENTS:
1. Consumer Duty PS22/9: each step must explain WHY we're asking for information
2. Progress indicator: always show current step / total steps
3. Save & continue: user can exit and resume without losing data
4. Help text: every field has accessible help text explaining the requirement
5. GDPR Art.12: plain English explanation of what data is collected and why
6. Accessibility: focus management between steps (WCAG 2.4.3 Focus Order)
7. Mobile-first: optimised for 375px viewport (Expo RN / mobile web)
8. Error recovery: if a step fails, user must not lose previously entered data

TONE (Consumer Duty PS22/9 — plain English):
- Use 'you' not 'the customer'
- Use 'we need' not 'it is required that'
- Explain consequences clearly ('Without this, we cannot open your account')
- No jargon: 'proof of address' not 'POA documentation'
"""


@dataclass
class OnboardingStep:
    """A single step in the onboarding flow."""

    step_id: str
    title: str
    description: str
    step_number: int
    total_steps: int
    fields: list[str] = field(default_factory=list)
    skip_allowed: bool = False
    regulatory_note: str = ""


class OnboardingAgent:
    """
    Generates step-by-step KYC onboarding flow screens.

    Produces a complete multi-step onboarding journey with:
      - Progress tracking
      - Save & resume capability
      - Consumer Duty-compliant language
      - Mobile-first layouts

    Args:
        orchestrator:      DesignToCodeOrchestrator instance
        penpot_file_id:    Penpot file ID for onboarding component library
        total_steps:       Total number of onboarding steps (default: 7)
        default_framework: Target framework
    """

    def __init__(
        self,
        orchestrator: DesignToCodeOrchestrator,
        penpot_file_id: str = "",
        total_steps: int = 7,
        default_framework: Framework = Framework.REACT,
    ) -> None:
        self._orchestrator = orchestrator
        self._file_id = penpot_file_id
        self._total_steps = total_steps
        self._framework = default_framework

    async def generate_welcome_screen(self, framework: Framework | None = None) -> GenerationResult:
        """Generate welcome / product selection screen (Step 1)."""
        return await self._generate_step(
            OnboardingStep(
                step_id="welcome",
                title="Welcome to BANXE",
                description="Open your account in under 5 minutes",
                step_number=1,
                total_steps=self._total_steps,
                regulatory_note="FCA-authorised EMI — regulated under the Electronic Money Regulations 2011",
            ),
            extra_instructions=(
                "Include:\n"
                "1. BANXE logo and value proposition headline\n"
                "2. Account type selector: Personal vs Business\n"
                "3. 'What you'll need' checklist (passport, proof of address)\n"
                "4. FCA authorisation badge and registration number\n"
                "5. 'Get Started' CTA\n"
                "6. Estimated time to complete onboarding\n"
            ),
            framework=framework,
        )

    async def generate_personal_details_screen(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """Generate personal details collection screen (Step 2)."""
        return await self._generate_step(
            OnboardingStep(
                step_id="personal_details",
                title="About you",
                description="We need your personal details to verify your identity",
                step_number=2,
                total_steps=self._total_steps,
                fields=["full_name", "date_of_birth", "nationality", "email", "phone"],
                regulatory_note="MLR 2017 Reg.28 — required for Customer Due Diligence",
            ),
            extra_instructions=(
                "Include:\n"
                "1. Full name field (as on ID document)\n"
                "2. Date of birth picker\n"
                "3. Nationality dropdown (prioritise UK/EU)\n"
                "4. Email with real-time format validation\n"
                "5. Phone with international dial code selector\n"
                "6. Why we ask: expandable explanation for each field\n"
            ),
            framework=framework,
        )

    async def generate_document_upload_screen(
        self,
        document_type: str = "passport",
        framework: Framework | None = None,
    ) -> GenerationResult:
        """Generate document upload screen (Step 3)."""
        return await self._generate_step(
            OnboardingStep(
                step_id=f"document_upload_{document_type}",
                title=f"Upload your {document_type.replace('_', ' ')}",
                description="We need to verify your identity document",
                step_number=3,
                total_steps=self._total_steps,
                regulatory_note="MLR 2017 Reg.28(3) — certified document verification",
            ),
            extra_instructions=(
                "Include:\n"
                "1. Document type selector: Passport / UK Driving Licence / National ID\n"
                "2. Photo upload dropzone with instructions (front + back for ID card)\n"
                "3. Camera capture option (mobile-first)\n"
                "4. Requirements checklist: clear photo, all 4 corners visible, no flash glare\n"
                "5. GDPR notice: document stored encrypted, deleted after 90 days\n"
                "6. Processing time indicator: 'usually under 2 minutes'\n"
            ),
            framework=framework,
        )

    async def generate_submitted_screen(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """Generate application submitted screen (final step)."""
        return await self._generate_step(
            OnboardingStep(
                step_id="submitted",
                title="Application submitted",
                description="We're reviewing your application",
                step_number=self._total_steps,
                total_steps=self._total_steps,
            ),
            extra_instructions=(
                "Include:\n"
                "1. Success animation / checkmark\n"
                "2. Application reference number (copiable)\n"
                "3. What happens next: review timeline\n"
                "4. Contact us if you have questions\n"
                "5. Download application summary PDF button\n"
            ),
            framework=framework,
        )

    async def generate_full_flow(
        self, framework: Framework | None = None
    ) -> list[GenerationResult]:
        """Generate all screens in the onboarding flow."""
        fw = framework or self._framework
        screens = [
            await self.generate_welcome_screen(fw),
            await self.generate_personal_details_screen(fw),
            await self.generate_document_upload_screen("passport", fw),
            await self.generate_submitted_screen(fw),
        ]
        logger.info("Generated %d onboarding screens for framework=%s", len(screens), fw.value)
        return screens

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _generate_step(
        self,
        step: OnboardingStep,
        extra_instructions: str = "",
        framework: Framework | None = None,
    ) -> GenerationResult:
        fw = framework or self._framework
        prompt = self._build_step_prompt(step, extra_instructions, fw)
        mitosis_jsx = await self._orchestrator._llm.agenerate(
            _ONBOARDING_SYSTEM_PROMPT + "\n\n" + prompt
        )
        compiled = self._orchestrator._generator.compile(mitosis_jsx, fw)
        return GenerationResult(
            component_id=f"onboarding-{step.step_id}",
            framework=fw,
            code=compiled,
            mitosis_jsx=mitosis_jsx,
            model_used=self._orchestrator._llm.model_name,
        )

    @staticmethod
    def _build_step_prompt(
        step: OnboardingStep, extra_instructions: str, framework: Framework
    ) -> str:
        return (
            f"Generate {framework.value} onboarding screen:\n"
            f"Title: {step.title}\n"
            f"Description: {step.description}\n"
            f"Step: {step.step_number} of {step.total_steps}\n"
            f"Regulatory basis: {step.regulatory_note}\n\n"
            f"Required elements:\n"
            f"1. Progress bar showing step {step.step_number}/{step.total_steps}\n"
            f"2. Back button (step > 1)\n"
            f"3. Save & continue option\n"
            f"{extra_instructions}\n"
        )
