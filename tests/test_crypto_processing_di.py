"""DI wiring tests for the crypto `processing` adapter selection (api/deps.py).

Covers: legacy default path, PAYBIS sandbox enabled path, and invalid/missing-env fallback.
Sandbox-only; no live calls. Tests the narrow selector `_select_crypto_processing_adapter`.
"""

from __future__ import annotations

from decimal import Decimal

from api.deps import _select_crypto_processing_adapter
from services.ledger.crypto_ledger_port import CryptoTransactionStatus, SupportedBlockchain
from services.ledger.legacy.legacy_crypto_processing_adapter import LegacyCryptoProcessingAdapter
from services.ledger.production.paybis_provider import PaybisProcessingShim

BTC = SupportedBlockchain.BTC


def _clear(monkeypatch):
    for var in ("PAYBIS_ENABLED", "PAYBIS_MODE"):
        monkeypatch.delenv(var, raising=False)


def test_legacy_default_path(monkeypatch):
    """No flag → legacy processing adapter (unchanged default behaviour)."""
    _clear(monkeypatch)
    processing = _select_crypto_processing_adapter()
    assert isinstance(processing, LegacyCryptoProcessingAdapter)


def test_paybis_sandbox_enabled_path(monkeypatch):
    """PAYBIS_ENABLED + sandbox → PAYBIS shim, callable on the processing port (create_tx/fee/health)."""
    monkeypatch.setenv("PAYBIS_ENABLED", "true")
    monkeypatch.setenv("PAYBIS_MODE", "sandbox")
    processing = _select_crypto_processing_adapter()
    assert isinstance(processing, PaybisProcessingShim)
    # processing-port surface works on the sandbox mock path
    assert processing.health() is True
    fee = processing.get_fee_estimate(BTC, Decimal("100.00"))
    assert fee.fee == Decimal("0.10")


def test_invalid_mode_falls_back_to_legacy(monkeypatch):
    """PAYBIS enabled but mode=production → refused → defensive fallback to legacy (no prod activation)."""
    monkeypatch.setenv("PAYBIS_ENABLED", "true")
    monkeypatch.setenv("PAYBIS_MODE", "production")
    processing = _select_crypto_processing_adapter()
    assert isinstance(processing, LegacyCryptoProcessingAdapter)


def test_disabled_flag_uses_legacy(monkeypatch):
    """Explicitly disabled → legacy."""
    monkeypatch.setenv("PAYBIS_ENABLED", "false")
    monkeypatch.setenv("PAYBIS_MODE", "sandbox")
    assert isinstance(_select_crypto_processing_adapter(), LegacyCryptoProcessingAdapter)


def test_wiring_failure_falls_back_to_legacy(monkeypatch):
    """Defensive: a PAYBIS wiring failure (build raises) → logged + legacy fallback, never breaks."""
    monkeypatch.setenv("PAYBIS_ENABLED", "true")
    monkeypatch.setenv("PAYBIS_MODE", "sandbox")
    import services.ledger.production.paybis_provider as prov

    def _boom() -> object:
        raise RuntimeError("simulated PAYBIS wiring failure")

    monkeypatch.setattr(prov, "build_sandbox_processing_adapter", _boom)
    processing = _select_crypto_processing_adapter()
    assert isinstance(processing, LegacyCryptoProcessingAdapter)


def test_paybis_shim_create_tx_returns_pending(monkeypatch):
    """Shim create_tx delegates to provider → PENDING result on the sandbox mock."""
    monkeypatch.setenv("PAYBIS_ENABLED", "true")
    monkeypatch.setenv("PAYBIS_MODE", "sandbox")
    from services.ledger.crypto_ledger_port import CryptoTransactionRequest, FeePriority

    processing = _select_crypto_processing_adapter()
    result = processing.create_tx(
        CryptoTransactionRequest(
            tx_id="di-1",
            from_wallet_id="w1",
            to_address="a1",
            blockchain=BTC,
            amount=Decimal("10.00"),
            currency="BTC",
            fee_level=FeePriority.MEDIUM,
            customer_id="c1",
        )
    )
    assert result.status is CryptoTransactionStatus.PENDING and result.tx_id == "di-1"
    # status poll + non-custodial boundary preserved through the shim
    assert processing.get_order_status("di-1") is CryptoTransactionStatus.PENDING
    from services.ledger.crypto_ledger_port import CryptoLedgerError

    for call in (
        lambda: processing.get_balance("w1", BTC),
        lambda: processing.create_wallet_address("c1", BTC),
    ):
        try:
            call()
            raise AssertionError("expected OUT_OF_PAYBIS_SCOPE")
        except CryptoLedgerError as e:
            assert e.code == "OUT_OF_PAYBIS_SCOPE"
