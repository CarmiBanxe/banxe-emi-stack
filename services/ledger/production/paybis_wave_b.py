"""PAYBIS Wave B — live-readiness scaffolding (FENCED). No live execution, no secrets, no funds.

Builds ON the Wave-A transport seam (`PaybisTransportPort`) WITHOUT enabling live HTTP. Provides the
PURE, testable building blocks a real transport will compose once SRC-06 (clean API spec) lands:

  - `build_order_request`  — frozen `CryptoTransactionRequest` → provider-neutral structural dict
                             (no HTTP, no secret, amount as Decimal-string, never float).
  - `normalize_order_response` — raw provider mapping → FROZEN `CryptoTransactionStatus`
                             (raises on malformed: not-a-dict / missing status).
  - `PaybisEndpoints` / `endpoint_for` — config-as-data routing PLACEHOLDERS (empty until SRC-06 →
                             fenced; never a guessed path).
  - `auth_headers`         — auth/header injection POINT — fenced (no secret read, no scheme guess)
                             until SRC-08. This is where real auth wires in Wave-B-live.

НЕИЗВЕСТНО (NOT invented here): endpoints, auth scheme, **signature algorithm**, exact request/
response schemas, fee %. Structural field names (partnerOrderId/transactionId/amount/status) are
SRC-05/06 FACT-from-preview. Nothing in this module performs I/O or moves funds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from services.ledger.crypto_ledger_port import (
    CryptoLedgerError,
    CryptoTransactionRequest,
    CryptoTransactionStatus,
)
from services.ledger.production.paybis_crypto_adapter import (
    PaybisConfig,
    PaybisLiveFencedError,
    map_order_status,
)


def build_order_request(request: CryptoTransactionRequest) -> dict[str, str]:
    """Frozen request → provider-neutral structural payload (PURE; no HTTP/secret/signature).

    Field NAMES are SRC-05/06 structural FACT (partnerOrderId/transactionId etc.); the wire format
    and signing are НЕИЗВЕСТНО and intentionally absent. I-01: amount stays Decimal → str (never float)."""
    if not isinstance(request.amount, Decimal):
        raise CryptoLedgerError("amount must be Decimal (I-01)", code="I01_DECIMAL")
    return {
        "partnerOrderId": request.tx_id,
        "blockchain": request.blockchain.value,
        "amount": str(request.amount),
        "currency": request.currency,
        "toAddress": request.to_address,
        "customerId": request.customer_id,
    }


def normalize_order_response(raw: Mapping[str, object]) -> CryptoTransactionStatus:
    """Raw provider response → FROZEN `CryptoTransactionStatus`. Raises on a malformed payload
    (not a mapping, or no status/state field) rather than silently defaulting — Wave B safety."""
    if not isinstance(raw, Mapping):
        raise CryptoLedgerError(
            "PAYBIS response is not a mapping", code="PAYBIS_MALFORMED_RESPONSE"
        )
    state = raw.get("status", raw.get("state"))
    if state is None or str(state).strip() == "":
        raise CryptoLedgerError(
            "PAYBIS response missing order status/state", code="PAYBIS_MALFORMED_RESPONSE"
        )
    return map_order_status(str(state))


@dataclass(frozen=True)
class PaybisEndpoints:
    """Endpoint routing PLACEHOLDERS (config-as-data). All empty until SRC-06 — никаких guessed
    paths. `op -> path` map is filled by the operator/spec, not invented here."""

    paths: dict[str, str] = field(default_factory=dict)

    def endpoint_for(self, config: PaybisConfig, op: str) -> str:
        """Resolve a full endpoint URL for `op`. FENCED while base_url or the op-path is unknown
        (НЕИЗВЕСТНО until SRC-06) — raises rather than returning a guessed URL."""
        path = self.paths.get(op, "")
        if not config.base_url or not path:
            raise PaybisLiveFencedError(f"endpoint_for({op})")
        return f"{config.base_url.rstrip('/')}/{path.lstrip('/')}"


def auth_headers(config: PaybisConfig) -> dict[str, str]:
    """Auth/header injection POINT for the future live transport. FENCED: no secret is read and no
    auth scheme is guessed (SRC-08 pending). Wave-B-live wires the real headers here."""
    raise PaybisLiveFencedError("auth_headers")
