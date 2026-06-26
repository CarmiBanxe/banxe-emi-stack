"""PAYBIS sandbox provider — thin feature-flag selector + runnable façade + smoke (sandbox-only).

The thinnest insertion that makes PAYBIS *runnable in project code today* without inventing literals.
Reuses the existing seam (ADR-102, no duplication): `PaybisCryptoAdapter` / `PaybisTransportPort` /
`paybis_webhook` / `paybis_sandbox`. NOT live: no real creds/secrets/endpoints/signature.

Capabilities (operator API ↔ Python snake_case façade):
  healthCheck()        -> health_check()
  getQuote(input)      -> get_quote(blockchain, amount)
  createOrder(input)   -> create_order(request)
  getOrderStatus(id)   -> get_order_status(order_id)
  handleWebhook(h,b)   -> handle_webhook(headers, body)

Feature flag / selection: `PAYBIS_ENABLED` + `PAYBIS_MODE=sandbox`. In sandbox with no real transport
the selector wires a **deterministic SandboxMockPaybisTransport** (mock fallback) so the smoke returns
structured results. Production mode is REFUSED here (OPERATOR-GATE).

НЕИЗВЕСТНО (NOT invented): endpoints, auth scheme, **signature algorithm**, payload schemas — fenced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import os
from typing import Any

from services.ledger.crypto_ledger_port import (
    CryptoFeeEstimate,
    CryptoLedgerError,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoTransactionStatus,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.production.paybis_crypto_adapter import (
    PaybisCryptoAdapter,
    PaybisTransportPort,
)
from services.ledger.production.paybis_sandbox import (
    PaybisSandboxError,
    PaybisSandboxWebhookSink,
    build_sandbox_config,
)


# ── feature flags / env contract (config-as-data; names only) ──────────────────────
@dataclass(frozen=True)
class PaybisFeatureFlags:
    """PAYBIS selection flags. VALUES from env; secrets (api key / webhook secret) are NAMES only."""

    enabled: bool = False
    mode: str = "sandbox"
    api_key_env: str = "PAYBIS_API_KEY"
    webhook_secret_env: str = "PAYBIS_WEBHOOK_SECRET"  # noqa: S105 — env-var NAME, not a secret value

    @classmethod
    def from_env(cls) -> PaybisFeatureFlags:
        return cls(
            enabled=os.environ.get("PAYBIS_ENABLED", "false").strip().lower()
            in {"1", "true", "yes"},
            mode=os.environ.get("PAYBIS_MODE", "sandbox").strip().lower(),
        )


def is_paybis_enabled() -> bool:
    """Feature-flag check: PAYBIS_ENABLED truthy."""
    return PaybisFeatureFlags.from_env().enabled


class SandboxMockPaybisTransport:
    """Deterministic SANDBOX mock transport (implements PaybisTransportPort). No live HTTP / secrets /
    funds — fixed structural responses so the seam is runnable. Replaced by a real transport at SRC-06."""

    def health(self) -> bool:
        return True

    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=Decimal("0.10"),
            currency="GBP",
            priority=FeePriority.MEDIUM,
            estimated_confirmation_blocks=3,
        )

    def initiate_order(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        return CryptoTransactionResult(
            tx_id=request.tx_id,
            tx_hash=None,
            blockchain=request.blockchain,
            amount=request.amount,
            fee=Decimal("0.10"),
            currency=request.currency,
            status=CryptoTransactionStatus.PENDING,
            from_wallet_id=request.from_wallet_id,
            to_address=request.to_address,
            created_at=datetime.now(UTC),
            confirmed_at=None,
        )

    def get_order_status(self, order_id: str) -> CryptoTransactionStatus:
        return CryptoTransactionStatus.PENDING


class PaybisSandboxProvider:
    """Thin runnable façade over the existing adapter + webhook sink. Sandbox-only."""

    def __init__(
        self,
        adapter: PaybisCryptoAdapter | None = None,
        sink: PaybisSandboxWebhookSink | None = None,
        transport: PaybisTransportPort | None = None,
    ) -> None:
        self._adapter = adapter or PaybisCryptoAdapter(
            transport=transport or SandboxMockPaybisTransport()
        )
        self._sink = sink or PaybisSandboxWebhookSink()

    def health_check(self) -> dict[str, Any]:  # operator: healthCheck()
        return {"provider": "paybis", "mode": "sandbox", "healthy": bool(self._adapter.health())}

    def get_quote(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:  # getQuote
        return self._adapter.get_fee_estimate(blockchain, amount)

    def create_order(
        self, request: CryptoTransactionRequest
    ) -> CryptoTransactionResult:  # createOrder
        return self._adapter.create_tx(request)

    def get_order_status(self, order_id: str) -> CryptoTransactionStatus:  # getOrderStatus
        return self._adapter.get_order_status(order_id)

    def handle_webhook(
        self, headers: dict[str, str], body: dict[str, Any]
    ) -> dict[str, Any]:  # handleWebhook
        """Idempotent sandbox intake. `headers` is reserved for signature verification (FENCED —
        OPERATOR-GATE on SRC-06 algorithm); events are recorded UNVERIFIED. Returns a normalized dict."""
        event = self._sink.intake(body)
        if event is None:
            return {"accepted": False, "duplicate": True, "verified": False}
        return {
            "accepted": True,
            "duplicate": False,
            "verified": False,  # signature algorithm НЕИЗВЕСТНО → never claim verified in sandbox
            "idempotency_key": event.idempotency_key,
            "status": event.status.value,
        }


def select_paybis_provider(transport: PaybisTransportPort | None = None) -> PaybisSandboxProvider:
    """Provider selector. Refuses when disabled or non-sandbox mode (OPERATOR-GATE: no prod). In
    sandbox with no real transport, wires the deterministic mock so the provider is runnable."""
    flags = PaybisFeatureFlags.from_env()
    if not flags.enabled:
        raise PaybisSandboxError(
            "PAYBIS disabled (set PAYBIS_ENABLED=true)", code="PAYBIS_DISABLED"
        )
    if flags.mode != "sandbox":
        raise PaybisSandboxError(
            f"PAYBIS mode '{flags.mode}' refused — sandbox install only (OPERATOR-GATE: no prod)",
            code="PAYBIS_SANDBOX_ONLY",
        )
    return PaybisSandboxProvider(transport=transport)


def normalize_error(exc: CryptoLedgerError) -> dict[str, str]:
    """Normalized error mapping at the adapter boundary (typed code + message)."""
    return {"error": exc.code or "PAYBIS_ERROR", "message": str(exc)}


def run_sandbox_smoke() -> dict[str, Any]:
    """Internal sandbox smoke: config loaded → provider selected → transport callable → mock/fenced
    path returns structured results. Forces sandbox flags locally so it always runs. No live calls."""
    os.environ.setdefault("PAYBIS_ENABLED", "true")
    os.environ.setdefault("PAYBIS_MODE", "sandbox")
    report: dict[str, Any] = {"steps": []}
    try:
        config = build_sandbox_config()  # OPERATOR-GATE if PAYBIS_ENV=PRODUCTION
        report["config_loaded"] = {"mode": config.env.value, "base_url_set": bool(config.base_url)}
        provider = select_paybis_provider()
        report["provider_selected"] = "paybis-sandbox"
        report["health"] = provider.health_check()
        quote = provider.get_quote(SupportedBlockchain.BTC, Decimal("100.00"))
        report["quote"] = {"fee": str(quote.fee), "currency": quote.currency}
        order = provider.create_order(
            CryptoTransactionRequest(
                tx_id="smoke-1",
                from_wallet_id="w1",
                to_address="addr1",
                blockchain=SupportedBlockchain.BTC,
                amount=Decimal("100.00"),
                currency="BTC",
                fee_level=FeePriority.MEDIUM,
                customer_id="cust-1",
            )
        )
        report["order"] = {"tx_id": order.tx_id, "status": order.status.value}
        report["order_status"] = provider.get_order_status("smoke-1").value
        report["webhook"] = provider.handle_webhook(
            {}, {"partnerOrderId": "smoke-1", "status": "completed"}
        )
        report["ok"] = True
    except CryptoLedgerError as exc:  # normalized boundary error
        report["ok"] = False
        report["error"] = normalize_error(exc)
    return report


if __name__ == "__main__":  # pragma: no cover - manual smoke entrypoint
    import json

    print(json.dumps(run_sandbox_smoke(), indent=2))
