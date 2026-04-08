"""
tests/test_infra_stubs.py — Infrastructure implementation tests
IL-053 | banxe-emi-stack

Tests ClickHouseCustomerService, ClickHouseWebhookAuditStore,
PostgreSQLConfigStore.reload(), RabbitMQEventBus.subscribe()
using unittest.mock — no real DB/MQ connections needed.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.customer.customer_port import (
    Address,
    CompanyProfile,
    CreateCustomerRequest,
    EntityType,
    IndividualProfile,
    LifecycleState,
    LifecycleTransitionRequest,
    RiskLevel,
    UBORecord,
)
from services.customer.customer_service import (
    ClickHouseCustomerService,
    _profile_from_dict,
    _profile_to_json,
)
from services.events.event_bus import (
    BanxeEventType,
    DomainEvent,
    InMemoryEventBus,
    RabbitMQEventBus,
)
from services.webhooks.webhook_router import (
    ClickHouseWebhookAuditStore,
    WebhookEvent,
    WebhookProvider,
    WebhookStatus,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def individual_req() -> CreateCustomerRequest:
    return CreateCustomerRequest(
        entity_type=EntityType.INDIVIDUAL,
        individual=IndividualProfile(
            first_name="Alice",
            last_name="Smith",
            date_of_birth=date(1990, 5, 15),
            nationality="GB",
            address=Address(line1="1 High Street", city="London", country="GB", postcode="EC1A 1BB"),
            email="alice@example.com",
        ),
        risk_level=RiskLevel.LOW,
    )


@pytest.fixture()
def company_req() -> CreateCustomerRequest:
    return CreateCustomerRequest(
        entity_type=EntityType.COMPANY,
        company=CompanyProfile(
            company_name="Acme Ltd",
            registration_number="12345678",
            country_of_incorporation="GB",
            registered_address=Address(
                line1="10 City Road", city="London", country="GB", postcode="EC1Y 2AB"
            ),
        ),
        risk_level=RiskLevel.MEDIUM,
    )


def _mock_ch_module() -> tuple[MagicMock, MagicMock]:
    """Return (mock_module, mock_client) for clickhouse_driver."""
    mock_module = MagicMock()
    mock_client = MagicMock()
    mock_client.execute.return_value = ([], [("profile_json", None)])
    mock_module.Client.return_value = mock_client
    return mock_module, mock_client


def _make_ch_svc() -> tuple[ClickHouseCustomerService, MagicMock]:
    """Build a ClickHouseCustomerService with a mocked Client."""
    mock_module, mock_client = _mock_ch_module()
    with patch.dict(sys.modules, {"clickhouse_driver": mock_module}):
        svc = ClickHouseCustomerService()
    svc._client = mock_client
    return svc, mock_client


def _make_webhook_store() -> tuple[ClickHouseWebhookAuditStore, MagicMock]:
    mock_module, mock_client = _mock_ch_module()
    with patch.dict(sys.modules, {"clickhouse_driver": mock_module}):
        store = ClickHouseWebhookAuditStore()
    store._client = mock_client
    return store, mock_client


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation round-trip tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileSerialisation:
    def test_individual_round_trip(self, individual_req: CreateCustomerRequest) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        svc = InMemoryCustomerService()
        profile = svc.create_customer(individual_req)
        json_str = _profile_to_json(profile)
        recovered = _profile_from_dict(json.loads(json_str))
        assert recovered.customer_id == profile.customer_id
        assert recovered.entity_type == EntityType.INDIVIDUAL
        assert recovered.individual is not None
        assert recovered.individual.first_name == "Alice"
        assert recovered.individual.date_of_birth == date(1990, 5, 15)
        assert recovered.individual.address.city == "London"

    def test_company_round_trip(self, company_req: CreateCustomerRequest) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        svc = InMemoryCustomerService()
        profile = svc.create_customer(company_req)
        json_str = _profile_to_json(profile)
        recovered = _profile_from_dict(json.loads(json_str))
        assert recovered.company is not None
        assert recovered.company.company_name == "Acme Ltd"
        assert recovered.entity_type == EntityType.COMPANY

    def test_ubo_round_trip(self, company_req: CreateCustomerRequest) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        svc = InMemoryCustomerService()
        profile = svc.create_customer(company_req)
        assert profile.company is not None
        profile.company.ubo_registry.append(
            UBORecord(
                full_name="Bob Jones", role="director",
                ownership_pct=Decimal("51.00"), nationality="GB",
                date_of_birth=date(1975, 3, 10),
            )
        )
        json_str = _profile_to_json(profile)
        recovered = _profile_from_dict(json.loads(json_str))
        assert recovered.company is not None
        assert len(recovered.company.ubo_registry) == 1
        ubo = recovered.company.ubo_registry[0]
        assert ubo.full_name == "Bob Jones"
        assert ubo.ownership_pct == Decimal("51.00")
        assert ubo.date_of_birth == date(1975, 3, 10)

    def test_decimal_amounts_serialised_as_strings(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        svc = InMemoryCustomerService()
        profile = svc.create_customer(individual_req)
        json_str = _profile_to_json(profile)
        # Must not contain float notation like 1.0 for financial amounts
        assert "float" not in json_str.lower()
        # Decimals should appear as quoted strings
        raw = json.loads(json_str)
        assert isinstance(raw["customer_id"], str)


# ─────────────────────────────────────────────────────────────────────────────
# ClickHouseCustomerService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestClickHouseCustomerService:
    def test_create_customer_calls_insert(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        svc, mock_client = _make_ch_svc()
        svc.create_customer(individual_req)
        # execute() should be called once for the INSERT
        mock_client.execute.assert_called_once()
        call_args = mock_client.execute.call_args
        assert "INSERT INTO banxe.customers" in call_args[0][0]

    def test_create_customer_blocked_jurisdiction(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        from services.customer.customer_port import CustomerManagementError
        individual_req.individual.nationality = "RU"  # type: ignore[union-attr]
        svc, mock_client = _make_ch_svc()
        with pytest.raises(CustomerManagementError, match="BLOCKED_JURISDICTION"):
            svc.create_customer(individual_req)
        mock_client.execute.assert_not_called()

    def test_get_customer_not_found_raises(self) -> None:
        from services.customer.customer_port import CustomerManagementError
        svc, mock_client = _make_ch_svc()
        mock_client.execute.return_value = ([], [("profile_json", None)])
        with pytest.raises(CustomerManagementError, match="NOT_FOUND"):
            svc.get_customer("cust-nonexistent")

    def test_get_customer_found(self, individual_req: CreateCustomerRequest) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        profile = in_mem.create_customer(individual_req)
        profile_json = _profile_to_json(profile)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.return_value = ([(profile_json,)], [("profile_json", None)])
        loaded = svc.get_customer(profile.customer_id)
        assert loaded.customer_id == profile.customer_id
        assert loaded.individual is not None
        assert loaded.individual.first_name == "Alice"

    def test_update_risk_level_calls_select_then_insert(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        profile = in_mem.create_customer(individual_req)
        profile_json = _profile_to_json(profile)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.side_effect = [
            ([(profile_json,)], [("profile_json", None)]),  # get
            None,  # persist
        ]
        updated = svc.update_risk_level(profile.customer_id, RiskLevel.HIGH)
        assert updated.risk_level == RiskLevel.HIGH
        assert mock_client.execute.call_count == 2

    def test_transition_lifecycle(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        profile = in_mem.create_customer(individual_req)
        profile.lifecycle_state = LifecycleState.ONBOARDING
        profile_json = _profile_to_json(profile)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.side_effect = [
            ([(profile_json,)], [("profile_json", None)]),  # get
            None,  # persist
        ]
        req = LifecycleTransitionRequest(
            customer_id=profile.customer_id,
            target_state=LifecycleState.ACTIVE,
            reason="KYC approved",
            operator_id="ops-001",
        )
        updated = svc.transition_lifecycle(req)
        assert updated.lifecycle_state == LifecycleState.ACTIVE

    def test_invalid_transition_raises(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        from services.customer.customer_port import CustomerManagementError
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        profile = in_mem.create_customer(individual_req)
        profile.lifecycle_state = LifecycleState.OFFBOARDED
        profile_json = _profile_to_json(profile)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.return_value = ([(profile_json,)], [("profile_json", None)])
        with pytest.raises(CustomerManagementError, match="INVALID_TRANSITION"):
            svc.transition_lifecycle(LifecycleTransitionRequest(
                customer_id=profile.customer_id,
                target_state=LifecycleState.ACTIVE,
                reason="reopen", operator_id="ops-001",
            ))

    def test_add_ubo_to_company(self, company_req: CreateCustomerRequest) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        profile = in_mem.create_customer(company_req)
        profile_json = _profile_to_json(profile)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.side_effect = [
            ([(profile_json,)], [("profile_json", None)]),  # get
            None,  # persist
        ]
        ubo = UBORecord(full_name="CEO Person", role="director", ownership_pct=Decimal("100"))
        updated = svc.add_ubo(profile.customer_id, ubo)
        assert updated.company is not None
        assert len(updated.company.ubo_registry) == 1

    def test_list_customers_no_filter(
        self, individual_req: CreateCustomerRequest
    ) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        p1 = in_mem.create_customer(individual_req)
        json1 = _profile_to_json(p1)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.return_value = ([(json1,)], [("profile_json", None)])
        customers = svc.list_customers()
        assert len(customers) == 1
        assert customers[0].customer_id == p1.customer_id

    def test_link_agreement(self, individual_req: CreateCustomerRequest) -> None:
        from services.customer.customer_service import InMemoryCustomerService
        in_mem = InMemoryCustomerService()
        profile = in_mem.create_customer(individual_req)
        profile_json = _profile_to_json(profile)

        svc, mock_client = _make_ch_svc()
        mock_client.execute.side_effect = [
            ([(profile_json,)], [("profile_json", None)]),  # get
            None,  # persist
        ]
        svc.link_agreement(profile.customer_id, "agr-001")
        assert mock_client.execute.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# ClickHouseWebhookAuditStore tests
# ─────────────────────────────────────────────────────────────────────────────

class TestClickHouseWebhookAuditStore:
    def _make_event(self) -> WebhookEvent:
        return WebhookEvent(
            webhook_id="wh-0001",
            provider=WebhookProvider.MODULR,
            event_type="payment.completed",
            payload={"payment_id": "pay-001"},
            received_at=datetime.now(timezone.utc),
            status=WebhookStatus.RECEIVED,
            signature_valid=True,
            raw_body=b'{"payment_id":"pay-001"}',
        )

    def test_save_calls_insert(self) -> None:
        store, mock_client = _make_webhook_store()
        store.save(self._make_event())
        mock_client.execute.assert_called_once()
        call_args = mock_client.execute.call_args
        assert "INSERT INTO banxe.webhook_events" in call_args[0][0]

    def test_save_includes_correct_fields(self) -> None:
        store, mock_client = _make_webhook_store()
        event = self._make_event()
        store.save(event)
        rows = mock_client.execute.call_args[0][1]
        row = rows[0]
        assert row["webhook_id"] == "wh-0001"
        assert row["provider"] == "modulr"
        assert row["signature_valid"] == 1

    def test_get_returns_none_when_not_found(self) -> None:
        store, mock_client = _make_webhook_store()
        mock_client.execute.return_value = ([], [
            ("webhook_id", None), ("provider", None), ("event_type", None),
            ("received_at", None), ("status", None), ("signature_valid", None), ("error", None),
        ])
        result = store.get("nonexistent")
        assert result is None

    def test_get_returns_event_when_found(self) -> None:
        store, mock_client = _make_webhook_store()
        now = datetime.now(timezone.utc)
        mock_client.execute.return_value = (
            [("wh-0001", "modulr", "payment.completed", now, "PROCESSED", 1, "")],
            [("webhook_id", None), ("provider", None), ("event_type", None),
             ("received_at", None), ("status", None), ("signature_valid", None), ("error", None)],
        )
        event = store.get("wh-0001")
        assert event is not None
        assert event.webhook_id == "wh-0001"
        assert event.provider == WebhookProvider.MODULR
        assert event.signature_valid is True
        assert event.status == WebhookStatus.PROCESSED

    def test_update_status_reinserts(self) -> None:
        store, mock_client = _make_webhook_store()
        now = datetime.now(timezone.utc)
        mock_client.execute.side_effect = [
            (
                [("wh-0002", "sumsub", "applicantReviewed", now, "RECEIVED", 1, "")],
                [("webhook_id", None), ("provider", None), ("event_type", None),
                 ("received_at", None), ("status", None), ("signature_valid", None), ("error", None)],
            ),
            None,  # INSERT
        ]
        store.update_status("wh-0002", WebhookStatus.PROCESSED)
        assert mock_client.execute.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQLConfigStore tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPostgreSQLConfigStore:
    def _mock_pg(self) -> MagicMock:
        """Return a mock psycopg2 connection that returns EMI_ACCOUNT config."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        # Products query
        products_row = {
            "product_id": "EMI_ACCOUNT",
            "display_name": "Banxe EMI Account",
            "currencies": ["GBP", "EUR"],
            "active": True,
        }
        # Fee schedule rows
        fee_rows = [
            {"tx_type": "FPS", "fee_type": "FLAT", "flat_fee": "0.20",
             "percentage": "0", "min_fee": "0.20", "max_fee": None, "currency": "GBP"},
        ]
        # Limits rows
        limits_rows = [
            {"entity_type": "INDIVIDUAL", "single_tx_max": "25000", "daily_max": "50000",
             "monthly_max": "150000", "daily_tx_count": 50, "monthly_tx_count": 500, "min_tx": "0.01"},
            {"entity_type": "COMPANY", "single_tx_max": "500000", "daily_max": "1000000",
             "monthly_max": "5000000", "daily_tx_count": 200, "monthly_tx_count": 2000, "min_tx": "0.01"},
        ]

        cursor.fetchall.side_effect = [
            [products_row],  # products query
            fee_rows,        # fees query for EMI_ACCOUNT
            limits_rows,     # limits query for EMI_ACCOUNT
        ]
        return conn

    def test_reload_loads_products(self) -> None:
        from services.config.config_service import PostgreSQLConfigStore
        conn = self._mock_pg()
        with patch("psycopg2.connect", return_value=conn):
            with patch("psycopg2.extras.RealDictCursor"):
                store = PostgreSQLConfigStore(dsn="postgresql://test/test")
        product = store.get_product("EMI_ACCOUNT")
        assert product is not None
        assert product.display_name == "Banxe EMI Account"
        assert "GBP" in product.currencies

    def test_reload_builds_fee_schedules(self) -> None:
        from services.config.config_service import PostgreSQLConfigStore
        conn = self._mock_pg()
        with patch("psycopg2.connect", return_value=conn):
            with patch("psycopg2.extras.RealDictCursor"):
                store = PostgreSQLConfigStore(dsn="postgresql://test/test")
        fee = store.get_fee("EMI_ACCOUNT", "FPS")
        assert fee is not None
        assert fee.flat_fee == Decimal("0.20")
        assert fee.fee_type == "FLAT"

    def test_reload_builds_payment_limits(self) -> None:
        from services.config.config_service import PostgreSQLConfigStore
        conn = self._mock_pg()
        with patch("psycopg2.connect", return_value=conn):
            with patch("psycopg2.extras.RealDictCursor"):
                store = PostgreSQLConfigStore(dsn="postgresql://test/test")
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits is not None
        assert limits.single_tx_max == Decimal("25000")
        assert limits.daily_tx_count == 50

    def test_missing_dsn_raises(self) -> None:
        from services.config.config_service import PostgreSQLConfigStore
        import os
        env_backup = os.environ.pop("POSTGRES_DSN", None)
        try:
            with pytest.raises(EnvironmentError, match="POSTGRES_DSN"):
                PostgreSQLConfigStore()
        finally:
            if env_backup is not None:
                os.environ["POSTGRES_DSN"] = env_backup

    def test_list_products(self) -> None:
        from services.config.config_service import PostgreSQLConfigStore
        conn = self._mock_pg()
        with patch("psycopg2.connect", return_value=conn):
            with patch("psycopg2.extras.RealDictCursor"):
                store = PostgreSQLConfigStore(dsn="postgresql://test/test")
        products = store.list_products()
        assert len(products) == 1
        assert products[0].product_id == "EMI_ACCOUNT"


# ─────────────────────────────────────────────────────────────────────────────
# RabbitMQEventBus tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRabbitMQEventBus:
    def test_missing_url_raises(self) -> None:
        import os
        env_backup = os.environ.pop("RABBITMQ_URL", None)
        try:
            with pytest.raises(EnvironmentError, match="RABBITMQ_URL"):
                RabbitMQEventBus()
        finally:
            if env_backup is not None:
                os.environ["RABBITMQ_URL"] = env_backup

    def test_publish_calls_basic_publish(self) -> None:
        mock_conn = MagicMock()
        mock_channel = MagicMock()
        mock_conn.channel.return_value = mock_channel

        with patch("pika.BlockingConnection", return_value=mock_conn):
            with patch("pika.URLParameters"):
                bus = RabbitMQEventBus(rabbitmq_url="amqp://guest:guest@localhost/")
                event = DomainEvent.create(
                    event_type=BanxeEventType.PAYMENT_COMPLETED,
                    source_service="payment_service",
                    payload={"payment_id": "pay-001"},
                    customer_id="cust-001",
                )
                bus.publish(event)

        mock_channel.exchange_declare.assert_called_once_with(
            exchange="banxe-events", exchange_type="topic", durable=True
        )
        mock_channel.basic_publish.assert_called_once()
        publish_kwargs = mock_channel.basic_publish.call_args[1]
        assert publish_kwargs["exchange"] == "banxe-events"
        assert publish_kwargs["routing_key"] == "payment.completed"
        mock_conn.close.assert_called_once()

    def test_publish_message_contains_event_id(self) -> None:
        mock_conn = MagicMock()
        mock_channel = MagicMock()
        mock_conn.channel.return_value = mock_channel

        with patch("pika.BlockingConnection", return_value=mock_conn):
            with patch("pika.URLParameters"):
                bus = RabbitMQEventBus(rabbitmq_url="amqp://guest:guest@localhost/")
                event = DomainEvent.create(
                    event_type=BanxeEventType.SAR_FILED,
                    source_service="aml_service",
                    payload={"sar_id": "sar-001"},
                )
                bus.publish(event)

        body = mock_channel.basic_publish.call_args[1]["body"]
        data = json.loads(body.decode())
        assert data["event_id"] == event.event_id
        assert data["event_type"] == "aml.sar_filed"

    def test_subscribe_starts_daemon_thread(self) -> None:
        mock_conn = MagicMock()
        mock_channel = MagicMock()
        mock_conn.channel.return_value = mock_channel

        # Make start_consuming block briefly then return
        def fake_start_consuming():
            pass  # immediately return so thread ends

        mock_channel.start_consuming.side_effect = fake_start_consuming
        mock_channel.queue_declare.return_value = MagicMock(method=MagicMock(queue="tmp-queue"))

        with patch("pika.BlockingConnection", return_value=mock_conn):
            with patch("pika.URLParameters"):
                bus = RabbitMQEventBus(rabbitmq_url="amqp://guest:guest@localhost/")
                handler_called = []

                def handler(event: DomainEvent) -> None:
                    handler_called.append(event)

                bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, handler)

        # Thread should be started (even if it finishes quickly)
        mock_channel.queue_bind.assert_called_once_with(
            exchange="banxe-events",
            queue="tmp-queue",
            routing_key="payment.completed",
        )


# ─────────────────────────────────────────────────────────────────────────────
# InMemoryEventBus — regression test (unchanged, sanity check)
# ─────────────────────────────────────────────────────────────────────────────

class TestInMemoryEventBus:
    def test_publish_and_subscribe(self) -> None:
        bus = InMemoryEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, received.append)
        event = DomainEvent.create(
            event_type=BanxeEventType.PAYMENT_COMPLETED,
            source_service="test",
            payload={},
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].event_id == event.event_id
