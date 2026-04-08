"""
sardine_adapter.py — Sardine.ai Live Fraud Scoring Adapter (stub)
S5-22 (Real-time fraud scoring <100ms) | S5-26 (APP scam detection PSR APP 2024)
PSR APP 2024 | banxe-emi-stack

WHY THIS EXISTS
---------------
Sardine.ai is the target fraud scoring provider for Banxe EMI.
This adapter is a stub — the API contract is correct but the live
HTTP call is not implemented until SARDINE_CLIENT_ID + SARDINE_SECRET_KEY
are provisioned (CEO action: contact sales@sardine.ai).

When keys arrive:
  1. Set FRAUD_ADAPTER=sardine in .env
  2. Set SARDINE_CLIENT_ID and SARDINE_SECRET_KEY in .env
  3. Uncomment and implement _call_sardine_api() below
  4. SardineFraudAdapter will be picked up automatically by get_fraud_adapter()

Sardine.ai API reference:
  - Docs: https://docs.sardine.ai (requires account)
  - Endpoint: POST /v1/customers/{customerId}/transactions/risk
  - Auth: HTTP Basic (client_id:secret_key)
  - SLA: < 100ms (enforced via timeout)
  - Response: risk level + score + rule_ids + APP_fraud_signal
"""
from __future__ import annotations

import logging
import os

from services.fraud.fraud_port import (
    FraudScoringPort,
    FraudScoringRequest,
    FraudScoringResult,
)

logger = logging.getLogger(__name__)

_SARDINE_API_BASE = os.environ.get("SARDINE_API_BASE", "https://api.sardine.ai/v1")
_SARDINE_TIMEOUT_MS = 100  # Hard SLA — never exceed 100ms (S5-22)


class SardineFraudAdapter:
    """
    Sardine.ai live fraud scoring adapter.
    Satisfies FraudScoringPort.

    STATUS: STUB — live HTTP call not implemented until API keys provisioned.
    Raises NotImplementedError to prevent accidental use in production.
    """

    def __init__(self) -> None:
        self._client_id = os.environ.get("SARDINE_CLIENT_ID", "")
        self._secret_key = os.environ.get("SARDINE_SECRET_KEY", "")
        if not self._client_id or not self._secret_key:
            raise EnvironmentError(
                "SARDINE_CLIENT_ID and SARDINE_SECRET_KEY must be set. "
                "Contact sales@sardine.ai to provision keys. "
                "Use FRAUD_ADAPTER=mock for sandbox mode."
            )

    def score(self, request: FraudScoringRequest) -> FraudScoringResult:
        # TODO: implement live Sardine.ai API call
        # Blocked on: SARDINE_CLIENT_ID + SARDINE_SECRET_KEY (CEO action)
        raise NotImplementedError(
            "SardineFraudAdapter.score() not yet implemented. "
            "Set FRAUD_ADAPTER=mock for sandbox testing."
        )

    def health(self) -> bool:
        # TODO: implement health check against Sardine.ai /health endpoint
        return False


def get_fraud_adapter() -> FraudScoringPort:
    """
    Factory: returns correct adapter based on FRAUD_ADAPTER env var.

    FRAUD_ADAPTER=mock    → MockFraudAdapter (default, always available)
    FRAUD_ADAPTER=jube    → JubeAdapter (self-hosted GMKtec :5001, AGPLv3)
    FRAUD_ADAPTER=sardine → SardineFraudAdapter (requires API keys, BT-004)
    """
    adapter_name = os.environ.get("FRAUD_ADAPTER", "mock").lower()
    if adapter_name == "jube":
        from services.fraud.jube_adapter import JubeAdapter
        return JubeAdapter()
    if adapter_name == "sardine":
        from services.fraud.sardine_adapter import SardineFraudAdapter  # noqa
        return SardineFraudAdapter()
    from services.fraud.mock_fraud_adapter import MockFraudAdapter
    return MockFraudAdapter()
