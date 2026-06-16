"""
modulr_sepa_stub.py — Production wiring stub for SEPA payments via Modulr Finance.

Satisfies PaymentRailPort structurally but raises NotImplementedError on all
network-touching methods. Marks the production integration surface for Wave C.

Canon: ADR-025 §15-16 + PaymentRailPort FROZEN (PORT-CONTRACTS-FREEZE-2026-05-08)
"""

from __future__ import annotations

from services.payment.payment_port import PaymentIntent, PaymentResult


class ModulrSepaStub:
    """
    Production stub: SEPA payment submission via Modulr Finance REST API.

    Requirements for production implementation:
      - Package dep: httpx>=0.27 (already in pyproject.toml)
      - Env vars: MODULR_API_KEY, MODULR_BASE_URL (e.g. https://api.modulrfinance.com)
      - Integration tests: run against Modulr sandbox environment
      - Implement submit_payment() via POST /v1/payments with HMAC-signed headers
      - Implement get_payment_status() via GET /v1/payments/{id}
      - Wire webhook handler (services/payment/webhook_handler.py) for async status updates

    Implement in a separate PR tagged [IL-SEPA-PROD-01].
    """

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        raise NotImplementedError(
            "ModulrSepaStub.submit_payment: not implemented. "
            "Requires MODULR_API_KEY + MODULR_BASE_URL env vars + httpx HTTP client. "
            "Implement in a dedicated production PR with Modulr sandbox integration tests."
        )

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        raise NotImplementedError(
            "ModulrSepaStub.get_payment_status: not implemented. "
            "Requires MODULR_API_KEY + MODULR_BASE_URL env vars. "
            "Implement in a dedicated production PR with Modulr sandbox integration tests."
        )

    def health(self) -> bool:
        raise NotImplementedError(
            "ModulrSepaStub.health: not implemented. "
            "Production: GET /v1/health against Modulr API with timeout guard."
        )
