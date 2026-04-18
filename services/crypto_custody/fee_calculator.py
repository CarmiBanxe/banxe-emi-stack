"""
services/crypto_custody/fee_calculator.py — Network and withdrawal fee calculations
IL-CDC-01 | Phase 35 | banxe-emi-stack
I-01: All amounts Decimal. Never float.
"""

from __future__ import annotations

from decimal import Decimal

from services.crypto_custody.models import AssetType, FeeEstimate, NetworkType

WITHDRAWAL_FEE_PCT = Decimal("0.001")  # 0.1%

NETWORK_FEE_ESTIMATES: dict[AssetType, Decimal] = {
    AssetType.BTC: Decimal("0.00010000"),
    AssetType.ETH: Decimal("0.00200000"),
    AssetType.USDT: Decimal("0.00300000"),
    AssetType.USDC: Decimal("0.00250000"),
    AssetType.SOL: Decimal("0.00005000"),
    AssetType.XRP: Decimal("0.00001000"),
    AssetType.DOGE: Decimal("0.50000000"),
}

MIN_AMOUNTS: dict[AssetType, Decimal] = {
    AssetType.BTC: Decimal("0.00010000"),
    AssetType.ETH: Decimal("0.00100000"),
    AssetType.USDT: Decimal("1.00000000"),
    AssetType.USDC: Decimal("1.00000000"),
    AssetType.SOL: Decimal("0.01000000"),
    AssetType.XRP: Decimal("0.10000000"),
    AssetType.DOGE: Decimal("1.00000000"),
}

MAX_AMOUNTS: dict[AssetType, Decimal] = {
    AssetType.BTC: Decimal("10.00000000"),
    AssetType.ETH: Decimal("100.00000000"),
    AssetType.USDT: Decimal("1000000.00000000"),
    AssetType.USDC: Decimal("1000000.00000000"),
    AssetType.SOL: Decimal("10000.00000000"),
    AssetType.XRP: Decimal("100000.00000000"),
    AssetType.DOGE: Decimal("5000000.00000000"),
}


class FeeCalculator:
    """Fee estimation and validation for crypto withdrawals (I-01: Decimal only)."""

    def estimate_network_fee(self, asset_type: AssetType, network: NetworkType) -> Decimal:
        """Get network fee estimate for asset (higher on MAINNET)."""
        base = NETWORK_FEE_ESTIMATES.get(asset_type, Decimal("0.00100000"))
        if network == NetworkType.TESTNET:
            return base * Decimal("2")
        return base

    def calculate_withdrawal_fee(self, amount: Decimal) -> Decimal:
        """Calculate 0.1% withdrawal fee (I-01: Decimal)."""
        return (amount * WITHDRAWAL_FEE_PCT).quantize(Decimal("0.00000001"))

    def get_total_fee(
        self, amount: Decimal, asset_type: AssetType, network: NetworkType
    ) -> FeeEstimate:
        """Return full FeeEstimate with network + withdrawal fees."""
        network_fee = self.estimate_network_fee(asset_type, network)
        withdrawal_fee = self.calculate_withdrawal_fee(amount)
        return FeeEstimate(
            asset_type=asset_type,
            network_fee=network_fee,
            withdrawal_fee=withdrawal_fee,
            total_fee=network_fee + withdrawal_fee,
            currency=asset_type.value,
        )

    def validate_min_amount(self, amount: Decimal, asset_type: AssetType) -> bool:
        """True if amount >= minimum for asset type."""
        minimum = MIN_AMOUNTS.get(asset_type, Decimal("0"))
        return amount >= minimum

    def validate_max_amount(self, amount: Decimal, asset_type: AssetType) -> bool:
        """True if amount <= maximum (10 BTC / 100 ETH / 1M stablecoin)."""
        maximum = MAX_AMOUNTS.get(asset_type, Decimal("999999999"))
        return amount <= maximum
