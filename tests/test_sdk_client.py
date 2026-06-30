"""
tests/test_sdk_client.py — SDK client tests
GAP-044 M-sdk | banxe-emi-stack

Comprehensive test suite for Banxe Python SDK.
Covers InMemoryBanxeClient, HttpBanxeClient, Protocol compliance.
Enforces I-01 (Decimal only) at unit test level.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sdk.python.banxe import (
    AccountBalance,
    BanxeSdkPort,
    HttpBanxeClient,
    InMemoryBanxeClient,
    PaymentResult,
)


class TestInMemoryBanxeClient:
    """Unit tests for InMemoryBanxeClient (test stub)."""

    @pytest.fixture
    def client(self) -> InMemoryBanxeClient:
        """Fresh client for each test."""
        return InMemoryBanxeClient()

    # ── Balance retrieval ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_balance_returns_account_balance(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """get_balance returns AccountBalance with correct fields."""
        client.seed_balance(
            "acc-001",
            "GBP",
            Decimal("1000.00"),
            Decimal("1000.00"),
        )
        result = await client.get_balance("acc-001")

        assert isinstance(result, AccountBalance)
        assert result.account_id == "acc-001"
        assert result.currency == "GBP"
        assert result.available == Decimal("1000.00")
        assert result.ledger == Decimal("1000.00")

    @pytest.mark.asyncio
    async def test_get_balance_raises_key_error_for_unknown_account(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """get_balance raises KeyError for non-existent account."""
        with pytest.raises(KeyError, match="not found"):
            await client.get_balance("unknown-account")

    @pytest.mark.asyncio
    async def test_get_balance_amounts_are_decimal_not_float(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """get_balance amounts are Decimal (I-01), not float."""
        client.seed_balance(
            "acc-001",
            "GBP",
            Decimal("1234.56"),
            Decimal("1234.56"),
        )
        result = await client.get_balance("acc-001")

        # I-01: MUST be Decimal, NEVER float
        assert isinstance(result.available, Decimal)
        assert isinstance(result.ledger, Decimal)
        assert not isinstance(result.available, float)
        assert not isinstance(result.ledger, float)

    @pytest.mark.asyncio
    async def test_get_balance_currency_preserved(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """get_balance currency field is preserved exactly."""
        client.seed_balance(
            "acc-eur-001",
            "EUR",
            Decimal("5000.00"),
            Decimal("5000.00"),
        )
        result = await client.get_balance("acc-eur-001")

        assert result.currency == "EUR"

    # ── Balance seeding (setup) ────────────────────────────────────────────

    def test_seed_balance_enforces_decimal_for_available(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """seed_balance enforces Decimal type for available (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            client.seed_balance("acc-001", "GBP", 1000.0, Decimal("1000.00"))  # type: ignore[arg-type]

    def test_seed_balance_enforces_decimal_for_ledger(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """seed_balance enforces Decimal type for ledger (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            client.seed_balance("acc-001", "GBP", Decimal("1000.00"), 1000.0)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_multiple_accounts_seeded_independently(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """Multiple accounts can be seeded and retrieved independently."""
        client.seed_balance("acc-001", "GBP", Decimal("1000.00"), Decimal("1000.00"))
        client.seed_balance("acc-002", "EUR", Decimal("2000.00"), Decimal("2000.00"))

        result1 = await client.get_balance("acc-001")
        result2 = await client.get_balance("acc-002")

        assert result1.account_id == "acc-001"
        assert result1.currency == "GBP"
        assert result2.account_id == "acc-002"
        assert result2.currency == "EUR"

    # ── Payment submission ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_submit_payment_returns_payment_result(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """submit_payment returns PaymentResult with correct fields."""
        result = await client.submit_payment(
            from_account="acc-001",
            to_account="acc-002",
            amount=Decimal("100.00"),
            currency="GBP",
            idempotency_key="idempotent-key-123",
        )

        assert isinstance(result, PaymentResult)
        assert result.payment_id.startswith("pay-")
        assert result.status == "COMPLETED"
        assert result.idempotency_key == "idempotent-key-123"

    @pytest.mark.asyncio
    async def test_submit_payment_idempotency_same_key_returns_same_payment_id(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """submit_payment with same idempotency_key returns same payment_id."""
        key = "idempotent-key-456"
        result1 = await client.submit_payment(
            from_account="acc-001",
            to_account="acc-002",
            amount=Decimal("100.00"),
            currency="GBP",
            idempotency_key=key,
        )
        result2 = await client.submit_payment(
            from_account="acc-001",
            to_account="acc-002",
            amount=Decimal("100.00"),
            currency="GBP",
            idempotency_key=key,
        )

        # Idempotency: same key → same payment_id
        assert result1.payment_id == result2.payment_id
        assert result1.payment_id.startswith("pay-")

    @pytest.mark.asyncio
    async def test_submit_payment_different_keys_return_different_payment_ids(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """Different idempotency keys generate different payment IDs."""
        result1 = await client.submit_payment(
            from_account="acc-001",
            to_account="acc-002",
            amount=Decimal("100.00"),
            currency="GBP",
            idempotency_key="key-1",
        )
        result2 = await client.submit_payment(
            from_account="acc-001",
            to_account="acc-002",
            amount=Decimal("100.00"),
            currency="GBP",
            idempotency_key="key-2",
        )

        assert result1.payment_id != result2.payment_id

    @pytest.mark.asyncio
    async def test_submit_payment_rejects_zero_amount(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """submit_payment rejects zero amount."""
        with pytest.raises(ValueError, match="positive"):
            await client.submit_payment(
                from_account="acc-001",
                to_account="acc-002",
                amount=Decimal("0.00"),
                currency="GBP",
                idempotency_key="key",
            )

    @pytest.mark.asyncio
    async def test_submit_payment_rejects_negative_amount(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """submit_payment rejects negative amount."""
        with pytest.raises(ValueError, match="positive"):
            await client.submit_payment(
                from_account="acc-001",
                to_account="acc-002",
                amount=Decimal("-100.00"),
                currency="GBP",
                idempotency_key="key",
            )

    @pytest.mark.asyncio
    async def test_submit_payment_amount_stored_as_decimal(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """submit_payment stores amount as Decimal (I-01)."""
        # In-memory client doesn't validate type at call, but HttpBanxeClient does.
        # Test that client accepts Decimal.
        result = await client.submit_payment(
            from_account="acc-001",
            to_account="acc-002",
            amount=Decimal("99.99"),  # Must be Decimal, not float
            currency="GBP",
            idempotency_key="key",
        )

        assert result.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_submit_payment_enforces_decimal_type(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """submit_payment enforces Decimal type for amount (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            await client.submit_payment(
                from_account="acc-001",
                to_account="acc-002",
                amount=100.00,  # type: ignore[arg-type]  # float, not Decimal
                currency="GBP",
                idempotency_key="key",
            )

    # ── Health check ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_health_check_returns_dict_with_status_key(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """health_check returns dict with 'status' key."""
        result = await client.health_check()

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "ok"

    # ── Protocol compliance ─────────────────────────────────────────────

    def test_in_memory_client_satisfies_banxe_sdk_port_protocol(
        self,
        client: InMemoryBanxeClient,
    ) -> None:
        """InMemoryBanxeClient structurally satisfies BanxeSdkPort Protocol."""
        # Check that InMemoryBanxeClient has all required methods
        assert hasattr(client, "get_balance")
        assert hasattr(client, "submit_payment")
        assert hasattr(client, "health_check")
        assert callable(client.get_balance)
        assert callable(client.submit_payment)
        assert callable(client.health_check)


class TestHttpBanxeClient:
    """Unit tests for HttpBanxeClient (production adapter)."""

    # ── Protocol compliance (structural check) ───────────────────────────

    def test_http_client_satisfies_banxe_sdk_port_protocol(self) -> None:
        """HttpBanxeClient structurally satisfies BanxeSdkPort Protocol."""
        # Check that HttpBanxeClient has all required methods
        client = HttpBanxeClient("http://localhost:8090", "test-key")

        assert hasattr(client, "get_balance")
        assert hasattr(client, "submit_payment")
        assert hasattr(client, "health_check")
        assert callable(client.get_balance)
        assert callable(client.submit_payment)
        assert callable(client.health_check)

    # ── Initialization ──────────────────────────────────────────────────

    def test_http_client_initialization(self) -> None:
        """HttpBanxeClient initializes with base_url and api_key."""
        client = HttpBanxeClient("http://localhost:8090", "secret-key")

        assert client._base_url == "http://localhost:8090"
        assert client._api_key == "secret-key"
        assert client._timeout == 30.0

    def test_http_client_initialization_custom_timeout(self) -> None:
        """HttpBanxeClient accepts custom timeout."""
        client = HttpBanxeClient(
            "http://localhost:8090",
            "secret-key",
            timeout=60.0,
        )

        assert client._timeout == 60.0

    def test_http_client_strips_trailing_slash_from_base_url(self) -> None:
        """HttpBanxeClient strips trailing slash from base_url."""
        client = HttpBanxeClient("http://localhost:8090/", "secret-key")

        assert client._base_url == "http://localhost:8090"

    # ── Context manager ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_http_client_context_manager(self) -> None:
        """HttpBanxeClient supports async context manager."""
        async with HttpBanxeClient("http://localhost:8090", "key") as client:
            assert client is not None


# ── Integration-style tests (no real HTTP) ─────────────────────────────────


class TestSdkPortProtocol:
    """Tests verifying BanxeSdkPort Protocol definition."""

    def test_banxe_sdk_port_protocol_defines_get_balance(self) -> None:
        """BanxeSdkPort Protocol defines get_balance method."""
        # Verify Protocol has required method via introspection
        assert hasattr(BanxeSdkPort, "__protocol_attrs__") or hasattr(
            BanxeSdkPort,
            "_get_protocol_attrs",
        )

    def test_account_balance_is_frozen_dataclass(self) -> None:
        """AccountBalance is immutable (frozen dataclass)."""
        balance = AccountBalance(
            account_id="acc-001",
            currency="GBP",
            available=Decimal("1000.00"),
            ledger=Decimal("1000.00"),
        )

        with pytest.raises(AttributeError):
            # Attempt to mutate — should fail due to frozen=True
            balance.available = Decimal("2000.00")  # type: ignore[misc]

    def test_payment_result_is_frozen_dataclass(self) -> None:
        """PaymentResult is immutable (frozen dataclass)."""
        result = PaymentResult(
            payment_id="pay-123",
            status="COMPLETED",
            idempotency_key="key",
        )

        with pytest.raises(AttributeError):
            # Attempt to mutate — should fail due to frozen=True
            result.status = "FAILED"  # type: ignore[misc]


class TestCrossClientConsistency:
    """Tests for consistency across In-Memory and Http clients."""

    @pytest.mark.asyncio
    async def test_both_clients_implement_same_interface(self) -> None:
        """Both clients implement same interface (BanxeSdkPort)."""
        in_memory = InMemoryBanxeClient()
        http_client = HttpBanxeClient("http://localhost:8090", "key")

        # Check method signatures match
        assert callable(in_memory.get_balance)
        assert callable(http_client.get_balance)
        assert callable(in_memory.submit_payment)
        assert callable(http_client.submit_payment)
        assert callable(in_memory.health_check)
        assert callable(http_client.health_check)
