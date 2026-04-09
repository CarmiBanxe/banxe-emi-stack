"""
config_service.py — Config-as-Data implementations
Geniusto v5 Pattern #6 — fees/limits/enums from store
FCA: COBS 6, PSR 2017 Reg.67

Implementations:
  YAMLConfigStore     — loads from config/banxe_config.yaml (default, no DB)
  InMemoryConfigStore — test-friendly, inject ProductConfig directly
  PostgreSQLConfigStore — stub (requires banxe PostgreSQL connection)

Factory:
  get_config_store()  — env-driven: CONFIG_STORE=yaml (default) | postgres
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path

from services.config.config_port import (
    ConfigPort,
    FeeSchedule,
    PaymentLimits,
    ProductConfig,
)

logger = logging.getLogger(__name__)

_DEFAULT_YAML = Path(__file__).parent.parent.parent / "config" / "banxe_config.yaml"


# ── YAML config store (primary) ────────────────────────────────────────────────


class YAMLConfigStore:
    """
    Loads product/fee/limit config from YAML.
    Supports runtime reload (call reload() to pick up YAML changes).

    Usage:
        store = YAMLConfigStore()           # loads config/banxe_config.yaml
        store = YAMLConfigStore("/path/to/custom.yaml")
        product = store.get_product("EMI_ACCOUNT")
        fee = store.get_fee("EMI_ACCOUNT", "FPS")   # FeeSchedule
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
    """

    def __init__(self, yaml_path: Path | None = None) -> None:
        self._path = yaml_path or _DEFAULT_YAML
        self._products: dict[str, ProductConfig] = {}
        self.reload()

    def reload(self) -> None:
        """(Re)load config from YAML file. Thread-safe for reads after load."""
        try:
            import yaml  # type: ignore[import]
        except ImportError:
            raise ImportError("Install PyYAML: pip install pyyaml")

        with open(self._path) as f:
            raw = yaml.safe_load(f)

        products: dict[str, ProductConfig] = {}
        for product_id, pcfg in (raw.get("products") or {}).items():
            fee_schedules = [
                FeeSchedule(
                    product_id=product_id,
                    tx_type=tx_type,
                    fee_type=fcfg["fee_type"],
                    flat_fee=Decimal(fcfg["flat_fee"]),
                    percentage=Decimal(fcfg["percentage"]),
                    min_fee=Decimal(fcfg["min_fee"]),
                    max_fee=Decimal(fcfg["max_fee"]) if fcfg.get("max_fee") else None,
                    currency=fcfg.get("currency", "GBP"),
                )
                for tx_type, fcfg in (pcfg.get("fees") or {}).items()
            ]

            limits_raw = pcfg.get("limits", {})

            def _build_limits(entity_type: str) -> PaymentLimits:
                lc = limits_raw.get(entity_type, {})
                return PaymentLimits(
                    product_id=product_id,
                    entity_type=entity_type,
                    single_tx_max=Decimal(lc.get("single_tx_max", "999999999")),
                    daily_max=Decimal(lc.get("daily_max", "999999999")),
                    monthly_max=Decimal(lc.get("monthly_max", "999999999")),
                    daily_tx_count=int(lc.get("daily_tx_count", 9999)),
                    monthly_tx_count=int(lc.get("monthly_tx_count", 99999)),
                    min_tx=Decimal(lc.get("min_tx", "0.01")),
                )

            products[product_id] = ProductConfig(
                product_id=product_id,
                display_name=pcfg.get("display_name", product_id),
                currencies=list(pcfg.get("currencies", ["GBP"])),
                fee_schedules=fee_schedules,
                individual_limits=_build_limits("INDIVIDUAL"),
                company_limits=_build_limits("COMPANY"),
                active=bool(pcfg.get("active", True)),
            )

        self._products = products
        logger.info("ConfigStore loaded %d products from %s", len(products), self._path)

    def get_product(self, product_id: str) -> ProductConfig | None:
        return self._products.get(product_id)

    def list_products(self) -> list[ProductConfig]:
        return list(self._products.values())

    def get_fee(self, product_id: str, tx_type: str) -> FeeSchedule | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        return product.get_fee(tx_type)

    def get_limits(self, product_id: str, entity_type: str) -> PaymentLimits | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        return product.get_limits(entity_type)


# ── In-memory config store (tests) ────────────────────────────────────────────


class InMemoryConfigStore:
    """
    Inject ProductConfig objects directly — for unit tests.

    Usage:
        store = InMemoryConfigStore([product_config_obj, ...])
    """

    def __init__(self, products: list[ProductConfig] | None = None) -> None:
        self._products: dict[str, ProductConfig] = {p.product_id: p for p in (products or [])}

    def get_product(self, product_id: str) -> ProductConfig | None:
        return self._products.get(product_id)

    def list_products(self) -> list[ProductConfig]:
        return list(self._products.values())

    def get_fee(self, product_id: str, tx_type: str) -> FeeSchedule | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        return product.get_fee(tx_type)

    def get_limits(self, product_id: str, entity_type: str) -> PaymentLimits | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        return product.get_limits(entity_type)

    def reload(self) -> None:
        pass  # no-op for in-memory


# ── PostgreSQL config store (stub — production) ───────────────────────────────


class PostgreSQLConfigStore:
    """
    Loads product/fee/limit config from PostgreSQL banxe schema.
    Supports hot-reload via LISTEN/NOTIFY (set POSTGRES_DSN env var).

    Schema: scripts/schema/postgres_config.sql
    Seed:   scripts/seed_postgres_config.py (or SQL seed in postgres_config.sql)

    Hot reload: call reload() manually or use LISTEN 'config_changed' in a
                background thread (triggered by banxe.config_version INSERT).
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or os.environ.get("POSTGRES_DSN", "")
        if not self._dsn:
            raise OSError(
                "POSTGRES_DSN not set. "
                "Example: postgresql://banxe:password@localhost:5432/banxe_compliance"
            )
        self._products: dict[str, ProductConfig] = {}
        self.reload()

    def reload(self) -> None:
        """
        (Re)load all products, fees, and limits from PostgreSQL.
        Thread-safe for reads after this method returns.
        """
        try:
            import psycopg2  # type: ignore[import]
            import psycopg2.extras  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("psycopg2 not installed: pip install psycopg2-binary") from exc

        conn = psycopg2.connect(self._dsn)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT product_id, display_name, currencies, active "
                    "FROM banxe.product_config WHERE active = TRUE"
                )
                products_raw = cur.fetchall()

                products: dict[str, ProductConfig] = {}
                for row in products_raw:
                    product_id = row["product_id"]

                    # ── Fees ──────────────────────────────────────────────────
                    cur.execute(
                        "SELECT tx_type, fee_type, flat_fee, percentage, "
                        "min_fee, max_fee, currency "
                        "FROM banxe.fee_schedule WHERE product_id = %s",
                        (product_id,),
                    )
                    fees = [
                        FeeSchedule(
                            product_id=product_id,
                            tx_type=r["tx_type"],
                            fee_type=r["fee_type"],
                            flat_fee=Decimal(str(r["flat_fee"])),
                            percentage=Decimal(str(r["percentage"])),
                            min_fee=Decimal(str(r["min_fee"])),
                            max_fee=Decimal(str(r["max_fee"]))
                            if r["max_fee"] is not None
                            else None,
                            currency=r["currency"],
                        )
                        for r in cur.fetchall()
                    ]

                    # ── Limits ────────────────────────────────────────────────
                    cur.execute(
                        "SELECT entity_type, single_tx_max, daily_max, monthly_max, "
                        "daily_tx_count, monthly_tx_count, min_tx "
                        "FROM banxe.payment_limits WHERE product_id = %s",
                        (product_id,),
                    )
                    limits_by_entity: dict[str, PaymentLimits] = {
                        r["entity_type"]: PaymentLimits(
                            product_id=product_id,
                            entity_type=r["entity_type"],
                            single_tx_max=Decimal(str(r["single_tx_max"])),
                            daily_max=Decimal(str(r["daily_max"])),
                            monthly_max=Decimal(str(r["monthly_max"])),
                            daily_tx_count=int(r["daily_tx_count"]),
                            monthly_tx_count=int(r["monthly_tx_count"]),
                            min_tx=Decimal(str(r["min_tx"])),
                        )
                        for r in cur.fetchall()
                    }

                    def _fallback_limits(entity_type: str) -> PaymentLimits:
                        return PaymentLimits(
                            product_id=product_id,
                            entity_type=entity_type,
                            single_tx_max=Decimal("999999999"),
                            daily_max=Decimal("999999999"),
                            monthly_max=Decimal("999999999"),
                            daily_tx_count=9999,
                            monthly_tx_count=99999,
                        )

                    products[product_id] = ProductConfig(
                        product_id=product_id,
                        display_name=row["display_name"],
                        currencies=list(row["currencies"]),
                        fee_schedules=fees,
                        individual_limits=limits_by_entity.get(
                            "INDIVIDUAL", _fallback_limits("INDIVIDUAL")
                        ),
                        company_limits=limits_by_entity.get("COMPANY", _fallback_limits("COMPANY")),
                        active=bool(row["active"]),
                    )

                self._products = products
                logger.info("PostgreSQLConfigStore: loaded %d products", len(products))
        finally:
            conn.close()

    def get_product(self, product_id: str) -> ProductConfig | None:
        return self._products.get(product_id)

    def list_products(self) -> list[ProductConfig]:
        return list(self._products.values())

    def get_fee(self, product_id: str, tx_type: str) -> FeeSchedule | None:
        p = self._products.get(product_id)
        return p.get_fee(tx_type) if p else None

    def get_limits(self, product_id: str, entity_type: str) -> PaymentLimits | None:
        p = self._products.get(product_id)
        return p.get_limits(entity_type) if p else None


# ── Factory ───────────────────────────────────────────────────────────────────


def get_config_store() -> ConfigPort:
    """Factory: CONFIG_STORE=yaml (default) | postgres."""
    backend = os.environ.get("CONFIG_STORE", "yaml").lower()
    if backend == "postgres":
        return PostgreSQLConfigStore()
    return YAMLConfigStore()
