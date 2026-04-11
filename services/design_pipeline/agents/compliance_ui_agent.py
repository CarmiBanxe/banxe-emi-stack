"""
services/design_pipeline/agents/compliance_ui_agent.py — Compliance UI Agent
IL-D2C-01 | BANXE EMI AI Bank

Generates KYC/AML compliance forms and screens from:
  - Penpot compliance component library
  - JSONSchema form definitions
  - FCA/GDPR/Consumer Duty regulatory requirements

FCA references:
  - Consumer Duty PS22/9: clear, fair, not misleading UI
  - GDPR Art.25: Privacy-by-Design in data collection forms
  - MLR 2017: Customer Due Diligence documentation requirements
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from services.design_pipeline.models import Framework, GenerationResult
from services.design_pipeline.orchestrator import DesignToCodeOrchestrator

logger = logging.getLogger("banxe.design_pipeline.agents.compliance_ui")

_COMPLIANCE_SYSTEM_PROMPT = """You are an expert compliance UI developer for BANXE AI Bank.
You generate FCA-compliant, GDPR-aware UI components that meet Consumer Duty PS22/9 requirements.

COMPLIANCE REQUIREMENTS:
1. GDPR Art.25 Privacy-by-Design: only collect minimum necessary data
2. Consumer Duty PS22/9: language must be clear, fair, and not misleading
3. FCA CASS 15: safeguarding disclosures must be prominently displayed
4. MLR 2017 CDD: document requirements must be clearly communicated
5. PSD2 SCA: strong authentication flows must be unambiguous
6. Accessibility: WCAG 2.1 AA compliance — all interactive elements keyboard-navigable
7. No dark patterns — no pre-ticked checkboxes for consent, no confusing opt-outs

FORBIDDEN PATTERNS:
- Hiding fees in small print (Consumer Duty)
- Pre-checking marketing consent boxes (GDPR)
- Ambiguous error messages that don't explain the compliance reason
- Form labels that misrepresent the purpose of data collection
"""


@dataclass
class ComplianceFormField:
    """A field definition for a compliance form."""

    name: str
    label: str
    input_type: str = "text"
    required: bool = True
    hint: str = ""
    purpose: str = ""  # GDPR purpose limitation
    validation_pattern: str = ""


@dataclass
class ComplianceFormSpec:
    """Specification for a compliance form to generate."""

    form_type: str  # kyc_individual | kyc_corporate | aml_declaration | sar_report
    title: str
    description: str = ""
    fields: list[ComplianceFormField] = field(default_factory=list)
    compliance_notices: list[str] = field(default_factory=list)
    regulatory_basis: list[str] = field(default_factory=list)


class ComplianceUIAgent:
    """
    Generates compliance UI components (KYC/AML forms, declarations, disclosures).

    Uses DesignToCodeOrchestrator with compliance-specific prompts
    that enforce GDPR, Consumer Duty, and FCA regulatory requirements.

    Args:
        orchestrator:       DesignToCodeOrchestrator instance
        penpot_file_id:     Penpot file ID for the compliance component library
        default_framework:  Target framework (default: React)
    """

    def __init__(
        self,
        orchestrator: DesignToCodeOrchestrator,
        penpot_file_id: str = "",
        default_framework: Framework = Framework.REACT,
    ) -> None:
        self._orchestrator = orchestrator
        self._file_id = penpot_file_id
        self._framework = default_framework

    async def generate_kyc_form(
        self,
        form_type: str = "kyc_individual",
        framework: Framework | None = None,
    ) -> GenerationResult:
        """
        Generate a KYC form component.

        Supported form_type values:
          - kyc_individual: Personal identity verification (passport, address)
          - kyc_corporate:  Business verification (articles, UBO, account purpose)
          - enhanced_dd:    Enhanced Due Diligence for high-risk customers
        """
        spec = self._get_kyc_spec(form_type)
        return await self._generate_from_spec(spec, framework or self._framework)

    async def generate_aml_declaration(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """Generate an AML funds source declaration form."""
        spec = ComplianceFormSpec(
            form_type="aml_declaration",
            title="Source of Funds Declaration",
            description="MLR 2017 requirement — all customers must declare source of funds",
            fields=[
                ComplianceFormField(
                    name="source_of_funds",
                    label="Primary source of funds",
                    input_type="select",
                    required=True,
                    purpose="AML/CFT risk assessment — MLR 2017 Reg.28",
                    hint="Select the primary source from which funds in this account originate",
                ),
                ComplianceFormField(
                    name="source_of_wealth",
                    label="Source of wealth",
                    input_type="textarea",
                    required=True,
                    purpose="EDD requirement for high-risk customers — MLR 2017 Reg.33",
                    hint="Briefly describe how you accumulated your total wealth",
                ),
                ComplianceFormField(
                    name="pep_declaration",
                    label="Are you, or have you ever been, a Politically Exposed Person (PEP)?",
                    input_type="radio",
                    required=True,
                    purpose="PEP screening — MLR 2017 Reg.35",
                ),
            ],
            compliance_notices=[
                "This information is required by the Money Laundering Regulations 2017 (MLR 2017).",
                "Providing false information is a criminal offence.",
            ],
            regulatory_basis=["MLR 2017", "JMLSG Guidance Part I"],
        )
        return await self._generate_from_spec(spec, framework or self._framework)

    async def generate_consent_screen(
        self,
        consent_type: str = "data_processing",
        framework: Framework | None = None,
    ) -> GenerationResult:
        """
        Generate a GDPR-compliant consent screen.

        Consumer Duty PS22/9: consent language must be plain English.
        GDPR Art.7: consent must be freely given, specific, informed, unambiguous.
        """
        spec = ComplianceFormSpec(
            form_type="gdpr_consent",
            title="Your Privacy Choices",
            description="GDPR Art.7 compliant consent — freely given, unambiguous",
            fields=[
                ComplianceFormField(
                    name="essential_processing",
                    label="Essential data processing for account operation",
                    input_type="checkbox",
                    required=True,
                    hint="Required to operate your BANXE account (cannot opt out)",
                    purpose="GDPR Art.6(1)(b) — contract performance",
                ),
            ],
            compliance_notices=[
                "You can withdraw consent at any time via Settings → Privacy.",
                "Withdrawal does not affect processing carried out before withdrawal.",
            ],
            regulatory_basis=["GDPR Art.6", "GDPR Art.7", "UK GDPR"],
        )
        return await self._generate_from_spec(spec, framework or self._framework)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _generate_from_spec(
        self, spec: ComplianceFormSpec, framework: Framework
    ) -> GenerationResult:
        """Generate code from a compliance form spec using the orchestrator."""
        prompt = self._build_compliance_prompt(spec, framework)

        # Inject compliance prompt directly into LLM
        mitosis_jsx = await self._orchestrator._llm.agenerate(
            _COMPLIANCE_SYSTEM_PROMPT + "\n\n" + prompt
        )

        compiled = self._orchestrator._generator.compile(mitosis_jsx, framework)

        return GenerationResult(
            component_id=f"compliance-{spec.form_type}",
            framework=framework,
            code=compiled,
            mitosis_jsx=mitosis_jsx,
            model_used=self._orchestrator._llm.model_name,
        )

    @staticmethod
    def _build_compliance_prompt(spec: ComplianceFormSpec, framework: Framework) -> str:
        fields_desc = "\n".join(
            f"  - {f.name} ({f.input_type}): {f.label} [{f.purpose}]" for f in spec.fields
        )
        notices = "\n".join(f"  - {n}" for n in spec.compliance_notices)
        regs = ", ".join(spec.regulatory_basis)

        return (
            f"Generate a {framework.value} compliance form for: {spec.title}\n\n"
            f"Form type: {spec.form_type}\n"
            f"Regulatory basis: {regs}\n\n"
            f"Fields:\n{fields_desc}\n\n"
            f"Required compliance notices to display:\n{notices}\n\n"
            f"Requirements:\n"
            f"1. Each field must have its regulatory purpose clearly visible to the user\n"
            f"2. No pre-ticked checkboxes for consent\n"
            f"3. Error messages must explain the compliance reason for each validation\n"
            f"4. Include WCAG 2.1 AA accessibility attributes\n"
            f"5. Add a compliance disclosure banner at the top of the form\n"
        )

    @staticmethod
    def _get_kyc_spec(form_type: str) -> ComplianceFormSpec:
        if form_type == "kyc_corporate":
            return ComplianceFormSpec(
                form_type="kyc_corporate",
                title="Business Verification",
                fields=[
                    ComplianceFormField(
                        name="company_name",
                        label="Registered company name",
                        required=True,
                        purpose="CDD — MLR 2017 Reg.28(10)(a)",
                    ),
                    ComplianceFormField(
                        name="company_number",
                        label="Companies House registration number",
                        required=True,
                        validation_pattern=r"^[A-Z0-9]{8}$",
                        purpose="CDD — MLR 2017 Reg.28(10)(b)",
                    ),
                    ComplianceFormField(
                        name="business_purpose",
                        label="Primary purpose of this account",
                        input_type="textarea",
                        required=True,
                        purpose="Account purpose — JMLSG Part I §5.7",
                    ),
                ],
                compliance_notices=[
                    "Business verification is required under MLR 2017.",
                    "Ultimate Beneficial Owners (>25% ownership) must be declared.",
                ],
                regulatory_basis=["MLR 2017", "JMLSG Part I", "FATF Recommendation 10"],
            )
        # Default: kyc_individual
        return ComplianceFormSpec(
            form_type="kyc_individual",
            title="Identity Verification",
            fields=[
                ComplianceFormField(
                    name="full_name",
                    label="Full legal name (as on ID document)",
                    required=True,
                    purpose="CDD — MLR 2017 Reg.28(2)(a)",
                ),
                ComplianceFormField(
                    name="date_of_birth",
                    label="Date of birth",
                    input_type="date",
                    required=True,
                    purpose="CDD — MLR 2017 Reg.28(2)(b)",
                ),
                ComplianceFormField(
                    name="nationality",
                    label="Nationality",
                    input_type="select",
                    required=True,
                    purpose="Jurisdictional risk — MLR 2017 Reg.33",
                ),
                ComplianceFormField(
                    name="address_postcode",
                    label="Current residential postcode",
                    required=True,
                    validation_pattern=r"^[A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2}$",
                    purpose="Address verification — MLR 2017 Reg.28(3)(b)",
                ),
            ],
            compliance_notices=[
                "Your identity is verified under the Money Laundering Regulations 2017.",
                "Documents are processed via our FCA-regulated KYC provider.",
            ],
            regulatory_basis=["MLR 2017", "JMLSG Part I", "FCA SYSC 3.2.6R"],
        )
