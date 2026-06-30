"""
sdk/python/banxe/http_client.py — Production HTTP adapter for Banxe SDK
GAP-044 M-sdk | banxe-emi-stack

HttpBanxeClient: makes real HTTP calls to Banxe API via httpx.
Implements BanxeSdkPort Protocol for dependency injection.
Handles Decimal parsing (I-01): API returns strings, parsed to Decimal locally.
"""

from __future__ import annotations

from decimal import Decimal

try:
    import httpx
except ImportError as exc:
    raise ImportError("httpx is required for HttpBanxeClient. Install: pip install httpx") from exc

from sdk.python.banxe.sdk_port import AccountBalance, PaymentResult


class HttpBanxeClient:
    """
    Production adapter — calls Banxe API via httpx.
    Handles authentication, error handling, decimal parsing.
    Implements BanxeSdkPort Protocol structurally.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize HTTP client.

        Args:
            base_url: Banxe API base URL (e.g., "http://localhost:8090")
            api_key: Bearer token for authentication
            timeout: Request timeout in seconds (default: 30.0)
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def get_balance(self, account_id: str) -> AccountBalance:
        """
        Fetch real-time balance for account.
        Raises httpx.HTTPStatusError if API returns error.
        Raises KeyError if account not found (404).
        """
        resp = await self._client.get(f"/v1/ledger/accounts/{account_id}/balance")

        if resp.status_code == 404:
            raise KeyError(f"Account {account_id!r} not found")

        resp.raise_for_status()
        data = resp.json()

        return AccountBalance(
            account_id=account_id,
            currency=data["currency"],
            available=Decimal(data["available"]),  # I-01: parse from string
            ledger=Decimal(data["total"]),  # I-01: parse from string
        )

    async def submit_payment(
        self,
        from_account: str,
        to_account: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> PaymentResult:
        """
        Submit a payment.
        Idempotency: same idempotency_key returns same payment_id.
        Raises httpx.HTTPStatusError if API returns error.
        Raises ValueError if amount <= 0.
        """
        if amount <= Decimal("0"):
            raise ValueError(f"Amount must be positive, got {amount}")

        resp = await self._client.post(
            "/v1/payments",
            json={
                "from_account": from_account,
                "to_account": to_account,
                "amount": str(amount),  # I-01: send as string (DecimalString)
                "currency": currency.upper(),
                "idempotency_key": idempotency_key,
                "customer_id": "sdk-client",
                "rail": "FPS",
                "reference": f"SDK payment {idempotency_key[:8]}",
                "debtor_account": {
                    "account_number": from_account,
                    "holder_name": "SDK Client",
                },
                "creditor_account": {
                    "account_number": to_account,
                    "holder_name": "Payment Recipient",
                },
            },
        )

        resp.raise_for_status()
        data = resp.json()

        return PaymentResult(
            payment_id=data["payment_id"],
            status=data["status"],
            idempotency_key=idempotency_key,
        )

    async def health_check(self) -> dict[str, str]:
        """
        Check API health.
        Returns dict with "status" key.
        Raises httpx.HTTPStatusError if API is down.
        """
        resp = await self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close HTTP client connection."""
        await self._client.aclose()

    async def __aenter__(self) -> HttpBanxeClient:
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Context manager exit — close client."""
        await self.close()
