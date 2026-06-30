"""
sdk/python/banxe — Banxe API Python Client SDK
GAP-044 M-sdk | banxe-emi-stack

Typed Python client for Banxe EMI API.
Protocol DI architecture: BanxeSdkPort → HttpBanxeClient (prod) + InMemoryBanxeClient (tests).

Key features:
  - All monetary values as Decimal (I-01: never float)
  - Idempotency for payment submissions
  - Async/await for all I/O
  - Full type hints (mypy compatible)
  - Hexagonal architecture for easy testing

Usage:
    from decimal import Decimal
    from sdk.python.banxe import InMemoryBanxeClient

    # In tests:
    client = InMemoryBanxeClient()
    client.seed_balance("acc-001", "GBP", Decimal("1000.00"), Decimal("1000.00"))
    balance = await client.get_balance("acc-001")
    print(balance.available)  # Decimal('1000.00')

    # In production:
    from sdk.python.banxe import HttpBanxeClient
    client = HttpBanxeClient(
        base_url="http://localhost:8090",
        api_key="secret-key"
    )
    async with client:
        balance = await client.get_balance("acc-001")
"""

from __future__ import annotations

from sdk.python.banxe.client import InMemoryBanxeClient
from sdk.python.banxe.http_client import HttpBanxeClient
from sdk.python.banxe.sdk_port import AccountBalance, BanxeSdkPort, PaymentResult

__all__ = [
    "AccountBalance",
    "BanxeSdkPort",
    "HttpBanxeClient",
    "InMemoryBanxeClient",
    "PaymentResult",
]
