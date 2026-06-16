"""
midaz_crypto_stub.py — Production wiring stub for crypto ledger operations via Midaz.

Satisfies CryptoLedgerPort structurally but raises NotImplementedError on all
network-touching methods. Marks the production integration surface for Wave E.

Canon: ADR-031 + ADR-025 §15-16 + CryptoLedgerPort FROZEN (PORT-CONTRACTS-FREEZE-2026-05-08)
"""

from __future__ import annotations

from decimal import Decimal

from services.ledger.crypto_ledger_port import (
    CryptoBalance,
    CryptoFeeEstimate,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoWalletAddress,
    SupportedBlockchain,
)


class MidazCryptoStub:
    """
    Production stub: crypto ledger operations via Midaz REST API.

    Requirements for production implementation:
      - Package dep: httpx>=0.27 (already in pyproject.toml)
      - Env vars: MIDAZ_API_KEY, MIDAZ_LEDGER_URL (e.g. http://midaz-api:8095)
      - Integration tests: run against Midaz sandbox (docker-compose.master.yml)
      - Implement create_tx() via POST /v1/transactions (idempotent on tx_id)
      - Implement get_balance() via GET /v1/wallets/{wallet_id}/balances
      - Implement create_wallet_address() via POST /v1/wallets

    Implement in a separate PR tagged [IL-CRYPTO-PROD-01].
    """

    def get_balance(
        self,
        wallet_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBalance:
        raise NotImplementedError(
            "MidazCryptoStub.get_balance: not implemented. "
            "Requires MIDAZ_API_KEY + MIDAZ_LEDGER_URL env vars. "
            "Implement in a dedicated production PR with Midaz sandbox integration tests."
        )

    def create_wallet_address(
        self,
        customer_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoWalletAddress:
        raise NotImplementedError(
            "MidazCryptoStub.create_wallet_address: not implemented. "
            "Requires MIDAZ_API_KEY + MIDAZ_LEDGER_URL env vars. "
            "Implement in a dedicated production PR with Midaz sandbox integration tests."
        )

    def create_tx(
        self,
        request: CryptoTransactionRequest,
    ) -> CryptoTransactionResult:
        raise NotImplementedError(
            "MidazCryptoStub.create_tx: not implemented. "
            "Requires MIDAZ_API_KEY + MIDAZ_LEDGER_URL env vars. "
            "Implement in a dedicated production PR with Midaz sandbox integration tests."
        )

    def get_fee_estimate(
        self,
        blockchain: SupportedBlockchain,
        amount: Decimal,
    ) -> CryptoFeeEstimate:
        raise NotImplementedError(
            "MidazCryptoStub.get_fee_estimate: not implemented. "
            "Requires MIDAZ_API_KEY + MIDAZ_LEDGER_URL env vars. "
            "Implement in a dedicated production PR with Midaz sandbox integration tests."
        )

    def health(self) -> bool:
        raise NotImplementedError(
            "MidazCryptoStub.health: not implemented. "
            "Production: GET /v1/health against Midaz API with timeout guard."
        )
