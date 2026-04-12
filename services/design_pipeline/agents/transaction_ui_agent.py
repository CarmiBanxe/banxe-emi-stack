"""
services/design_pipeline/agents/transaction_ui_agent.py — Transaction UI Agent
IL-D2C-01 | BANXE EMI AI Bank

Generates payment flow screens with PSD2 SCA requirements:
  - Payment initiation forms (SEPA, FPS, BACS)
  - SCA challenge screens (TOTP, biometric)
  - Payment confirmation and receipt screens
  - Beneficiary management UI

PSD2 SCA references:
  - RTS on SCA Art.4: Dynamic linking requirement
  - PSD2 Art.97: Authentication requirements
  - PSR APP 2024: UK SCA implementation
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from services.design_pipeline.models import Framework, GenerationResult
from services.design_pipeline.orchestrator import DesignToCodeOrchestrator

logger = logging.getLogger("banxe.design_pipeline.agents.transaction_ui")

_PSD2_SYSTEM_PROMPT = """You are a PSD2-compliant payment UI developer for BANXE AI Bank.

PSD2 SCA REQUIREMENTS:
1. RTS Art.4 Dynamic Linking: payment confirmation must show amount AND payee
2. RTS Art.4: If amount changes, SCA must be repeated
3. Strong authentication: display which factor is being used (possession, knowledge, inherence)
4. Session timeout: warn user 60s before session expiry
5. Confirmation screens: must be unambiguous — no ability to accidentally confirm
6. Accessibility: payment amounts must have sufficient contrast (WCAG 4.5:1)
7. PSR APP 2024: fraud warnings for high-risk payment patterns

FORBIDDEN:
- Hiding payment details in the SCA confirmation step
- Allowing payment amount modification after SCA started
- Storing sensitive payment data in browser storage
"""


@dataclass
class PaymentFlowSpec:
    """Specification for a payment flow screen."""

    flow_type: str  # initiation | sca_challenge | confirmation | receipt | beneficiary
    payment_rail: str = "fps"  # fps | bacs | sepa_ct | sepa_instant | swift
    currency: str = "GBP"
    requires_sca: bool = True


class TransactionUIAgent:
    """
    Generates PSD2-compliant payment flow UI components.

    Each screen in the payment flow is generated with:
      - Dynamic linking (RTS Art.4)
      - SCA challenge integration
      - Fraud warning banners where required
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

    async def generate_payment_initiation(
        self,
        rail: str = "fps",
        framework: Framework | None = None,
    ) -> GenerationResult:
        """
        Generate payment initiation form.

        Includes:
          - Beneficiary lookup (sort code / IBAN)
          - Amount entry with currency selection
          - Reference / description field
          - Payment reference for dynamic linking
        """
        prompt = (
            f"{_PSD2_SYSTEM_PROMPT}\n\n"
            f"Generate a {rail.upper()} payment initiation form with:\n"
            f"1. Beneficiary name + sort code/account (or IBAN for SEPA)\n"
            f"2. Amount field (Decimal, not float — use string representation)\n"
            f"3. Payment reference field (max 18 chars for FPS)\n"
            f"4. Estimated arrival time for the {rail.upper()} rail\n"
            f"5. 'Review Payment' CTA (not 'Send' — dynamic linking requires explicit confirmation)\n"
            f"6. Fraud warning banner if amount > £1000\n"
        )
        return await self._generate_screen("payment_initiation", prompt, framework)

    async def generate_sca_challenge(
        self,
        method: str = "totp",
        framework: Framework | None = None,
    ) -> GenerationResult:
        """
        Generate SCA challenge screen.

        PSD2 RTS Art.4: must display amount and payee for dynamic linking.
        Supported methods: totp | sms_otp | biometric | push_notification
        """
        prompt = (
            f"{_PSD2_SYSTEM_PROMPT}\n\n"
            f"Generate a PSD2 SCA challenge screen using {method.upper()} method:\n"
            f"1. Summary banner showing: AMOUNT + PAYEE NAME (dynamic linking RTS Art.4)\n"
            f"2. {method.upper()} input field with countdown timer (30s for TOTP)\n"
            f"3. 'Authenticate' button — disabled until code entered\n"
            f"4. 'Cancel payment' link — must be clearly visible\n"
            f"5. 'Resend code' link (for SMS OTP, throttled at 3 attempts)\n"
            f"6. Warning: 'Never share this code with anyone, including BANXE staff'\n"
        )
        return await self._generate_screen("sca_challenge", prompt, framework)

    async def generate_payment_confirmation(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """
        Generate payment confirmation screen (post-SCA).

        Shows final payment details for user to confirm before submission.
        """
        prompt = (
            f"{_PSD2_SYSTEM_PROMPT}\n\n"
            f"Generate a payment confirmation screen:\n"
            f"1. Summary card: payee, amount, reference, estimated arrival\n"
            f"2. Exchange rate disclosure if cross-currency payment\n"
            f"3. 'Confirm & Send' primary CTA + 'Cancel' secondary button\n"
            f"4. Legal disclosure: payment is irrevocable once confirmed\n"
            f"5. Session expiry warning at bottom of screen\n"
        )
        return await self._generate_screen("payment_confirmation", prompt, framework)

    async def generate_payment_receipt(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """Generate payment receipt screen with audit trail reference."""
        prompt = (
            f"{_PSD2_SYSTEM_PROMPT}\n\n"
            f"Generate a payment receipt screen:\n"
            f"1. Success confirmation with green checkmark\n"
            f"2. Payment ID / reference number (copiable)\n"
            f"3. Full payment details summary\n"
            f"4. 'Download PDF' and 'Share' buttons\n"
            f"5. 'Back to dashboard' CTA\n"
        )
        return await self._generate_screen("payment_receipt", prompt, framework)

    async def _generate_screen(
        self, screen_type: str, prompt: str, framework: Framework | None
    ) -> GenerationResult:
        fw = framework or self._framework
        mitosis_jsx = await self._orchestrator._llm.agenerate(prompt)
        compiled = self._orchestrator._generator.compile(mitosis_jsx, fw)
        return GenerationResult(
            component_id=f"transaction-{screen_type}",
            framework=fw,
            code=compiled,
            mitosis_jsx=mitosis_jsx,
            model_used=self._orchestrator._llm.model_name,
        )
