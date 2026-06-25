"""PaybisCryptoAdapter — PAYBIS-first crypto on/off-ramp behind the FROZEN CryptoLedgerPort.

Wave A (smallest safe slice). Governance: ADR-126 (NeuroNext retired, PAYBIS sole external
crypto provider), ADR-108 (Paybis = MiCA CASP, distribution/processor split, **non-custodial**),
ADR-114 (Travel Rule on Paybis; go-live gate). PAYBIS-only — no dual-provider logic.

Design (Wave A):
  - Implements the FROZEN `CryptoLedgerPort` (port UNCHANGED) alongside `MidazCryptoAdapter`.
  - **Mock-first / live-fenced:** all PAYBIS calls go through an injectable `PaybisTransportPort`.
    The default `FencedLivePaybisTransport` raises `PaybisLiveFencedError` — **no live HTTP, no
    secrets, no funds movement** until SRC-06 (clean API spec) + ADR-114 go-live gate are closed.
  - **Non-custodial boundary (ADR-108):** PAYBIS does on/off-ramp orders + fees + status, NOT
    custody. `get_balance` / `create_wallet_address` raise `OUT_OF_PAYBIS_SCOPE` (wallet/balance
    are on-chain/Midaz concerns) — not faked.
  - I-01: amounts are Decimal only. I-24: results are the FROZEN immutable dataclasses.

НЕИЗВЕСТНО (SRC-06 pending — not invented here): endpoints, auth, signature algorithm,
request/response schemas, webhook payload, rate-limit/SLA, fee %, sandbox/prod base-URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import os
from typing import Protocol, runtime_checkable

from services.ledger.crypto_ledger_port import (
    CryptoFeeEstimate,
    CryptoLedgerError,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoTransactionStatus,
    SupportedBlockchain,
)


class PaybisEnv(StrEnum):
    """PAYBIS environment (config-as-data; selects sandbox vs prod transport)."""

    SANDBOX = "SANDBOX"
    PRODUCTION = "PRODUCTION"


# PAYBIS order lifecycle states (SRC-05/06 structural FACT-from-preview) → FROZEN status.
# pending → PENDING; completed → CONFIRMED; cancelled/rejected/expired/refunded → FAILED.
_PAYBIS_STATE_MAP: dict[str, CryptoTransactionStatus] = {
    "pending": CryptoTransactionStatus.PENDING,
    "completed": CryptoTransactionStatus.CONFIRMED,
    "cancelled": CryptoTransactionStatus.FAILED,
    "rejected": CryptoTransactionStatus.FAILED,
    "expired": CryptoTransactionStatus.FAILED,
    "refunded": CryptoTransactionStatus.FAILED,
}


def map_order_status(paybis_state: str) -> CryptoTransactionStatus:
    """Map a PAYBIS order state to the FROZEN CryptoTransactionStatus. Unknown → PENDING (safe)."""
    return _PAYBIS_STATE_MAP.get(str(paybis_state).lower().strip(), CryptoTransactionStatus.PENDING)


@dataclass(frozen=True)
class PaybisConfig:
    """PAYBIS adapter config (config-as-data). No secret values are stored here — only the NAME
    of the env var holding the API key; the key is read at transport time (I-SEC)."""

    env: PaybisEnv = PaybisEnv.SANDBOX
    base_url: str = ""  # resolved from env; empty until SRC-06/operator provides (НЕИЗВЕСТНО)
    api_key_env_var: str = "PAYBIS_API_KEY"  # variable NAME, never the value

    @classmethod
    def from_env(cls) -> PaybisConfig:
        """Build config from environment (no secret persisted). base_url from PAYBIS_BASE_URL."""
        env_raw = os.environ.get("PAYBIS_ENV", PaybisEnv.SANDBOX.value).upper()
        env = PaybisEnv(env_raw) if env_raw in PaybisEnv.__members__ else PaybisEnv.SANDBOX
        return cls(env=env, base_url=os.environ.get("PAYBIS_BASE_URL", ""))


class PaybisLiveFencedError(CryptoLedgerError):
    """Raised by the fenced live transport: live PAYBIS calls are disabled in Wave A."""

    def __init__(self, op: str) -> None:
        super().__init__(
            f"PAYBIS live transport is fenced in Wave A (op={op}); requires SRC-06 API spec "
            "+ ADR-114 go-live gate (TR contract + MLRO). No secrets/funds in Wave A.",
            code="PAYBIS_LIVE_FENCED",
        )


@runtime_checkable
class PaybisTransportPort(Protocol):
    """Injectable PAYBIS transport seam. Wave A: a mock implements it for tests; the default
    live transport is fenced. Method shapes are structural (SRC-05/06); literal API НЕИЗВЕСТНО."""

    def health(self) -> bool: ...
    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate: ...
    def initiate_order(self, request: CryptoTransactionRequest) -> CryptoTransactionResult: ...


class FencedLivePaybisTransport:
    """Default transport — every call is fenced (no live HTTP, no secrets, no funds). Wave B
    replaces this with a real transport once SRC-06 (clean API spec) is available."""

    def __init__(self, config: PaybisConfig | None = None) -> None:
        self._config = config or PaybisConfig()

    def health(self) -> bool:
        raise PaybisLiveFencedError("health")

    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:
        raise PaybisLiveFencedError("get_fee_estimate")

    def initiate_order(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        raise PaybisLiveFencedError("initiate_order")


class PaybisCryptoAdapter:
    """CryptoLedgerPort adapter routing crypto on/off-ramp through PAYBIS (sole provider, ADR-126).

    Wave A capabilities: health, get_fee_estimate, create_tx (initiate BuyCrypto/SellCrypto order
    → PENDING). get_balance / create_wallet_address are out of PAYBIS scope (non-custodial, ADR-108).
    """

    def __init__(
        self,
        transport: PaybisTransportPort | None = None,
        config: PaybisConfig | None = None,
    ) -> None:
        self._config = config or PaybisConfig()
        self._transport = transport or FencedLivePaybisTransport(self._config)

    # ── CryptoLedgerPort ──────────────────────────────────────────────────────
    def health(self) -> bool:
        """Provider availability via PAYBIS transport."""
        return bool(self._transport.health())

    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:
        """Fee/quote estimate for an on/off-ramp transfer. I-01: amount must be Decimal."""
        if not isinstance(amount, Decimal):
            raise CryptoLedgerError("amount must be Decimal (I-01)", code="I01_DECIMAL")
        return self._transport.get_fee_estimate(blockchain, amount)

    def create_tx(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        """Initiate a PAYBIS order (BuyCrypto/SellCrypto). I-01: amount Decimal; idempotent on
        request.tx_id (mapped to PAYBIS partnerOrderId by the transport). Returns a PENDING result;
        terminal status arrives via webhook (see paybis_webhook). Live path is fenced (no funds)."""
        if not isinstance(request.amount, Decimal):
            raise CryptoLedgerError("amount must be Decimal (I-01)", code="I01_DECIMAL")
        if request.amount <= Decimal("0"):
            raise CryptoLedgerError("amount must be positive", code="AMOUNT_NONPOSITIVE")
        return self._transport.initiate_order(request)

    def get_balance(self, wallet_id: str, blockchain: SupportedBlockchain):  # noqa: ANN201
        """Out of PAYBIS scope: BANXE is non-custodial (ADR-108) — wallet balance is an on-chain /
        Midaz concern, not PAYBIS. Raised rather than faked."""
        raise CryptoLedgerError(
            "get_balance is out of PAYBIS scope (non-custodial, ADR-108): use on-chain/Midaz",
            code="OUT_OF_PAYBIS_SCOPE",
        )

    def create_wallet_address(self, customer_id: str, blockchain: SupportedBlockchain):  # noqa: ANN201
        """Out of PAYBIS scope: address derivation is non-custodial wallet / on-chain, not PAYBIS."""
        raise CryptoLedgerError(
            "create_wallet_address is out of PAYBIS scope (non-custodial, ADR-108)",
            code="OUT_OF_PAYBIS_SCOPE",
        )
