"""
resolution_pack.py — CASS 10A Resolution Pack Builder
S6-14 | CASS 10A | FCA Client Assets Sourcebook | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
FCA CASS 10A requires Electronic Money Institutions to be able to retrieve
a complete resolution pack within 48 hours of a resolution event (insolvency
or wind-down). The pack must contain:
  - Client money statement (positions by customer)
  - Outstanding payment records
  - Safeguarding reconciliation summary
  - Audit event log snapshot

This module builds the resolution pack on demand from ClickHouse records.
Pack is returned as a structured dict (serialisable to JSON) and can be
exported to ZIP (CSV + JSON manifest) via build_zip().

FCA rules:
  - CASS 10A.3.1R: resolution pack must be retrievable within 48 hours
  - CASS 10A.3.2R: must include client money statement and records
  - MLR 2017: records must be retained 5 years (I-08)
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

# ── Domain types ──────────────────────────────────────────────────────────────


@dataclass
class ClientMoneyPosition:
    """Single customer's safeguarded balance at resolution point."""

    customer_id: str
    currency: str
    balance: Decimal
    last_updated: datetime
    account_id: str | None = None


@dataclass
class ResolutionPack:
    """
    CASS 10A resolution pack snapshot.
    Generated on demand; must be retrievable within 48h.
    """

    generated_at: datetime
    as_of_date: datetime
    total_client_money: Decimal
    currency: str
    positions: list[ClientMoneyPosition]
    outstanding_payments: list[dict]  # payment records pending settlement
    reconciliation_summary: dict  # last recon result
    audit_events_count: int
    pack_version: str = "1.0"
    fca_rule: str = "CASS 10A.3.1R"

    def to_manifest(self) -> dict:
        return {
            "pack_version": self.pack_version,
            "fca_rule": self.fca_rule,
            "generated_at": self.generated_at.isoformat(),
            "as_of_date": self.as_of_date.isoformat(),
            "total_client_money": str(self.total_client_money),
            "currency": self.currency,
            "position_count": len(self.positions),
            "outstanding_payment_count": len(self.outstanding_payments),
            "audit_events_count": self.audit_events_count,
            "reconciliation_summary": self.reconciliation_summary,
        }


# ── Repository protocol (testable without ClickHouse) ─────────────────────────


class ResolutionDataRepository(Protocol):
    def get_client_money_positions(self, as_of: datetime) -> list[ClientMoneyPosition]: ...
    def get_outstanding_payments(self, as_of: datetime) -> list[dict]: ...
    def get_reconciliation_summary(self, as_of: datetime) -> dict: ...
    def get_audit_events_count(self, as_of: datetime) -> int: ...


# ── In-memory repository for tests / dry-run ──────────────────────────────────


class InMemoryResolutionRepository:
    """Deterministic stub — no ClickHouse required."""

    def __init__(
        self,
        positions: list[ClientMoneyPosition] | None = None,
        outstanding: list[dict] | None = None,
        recon: dict | None = None,
        audit_count: int = 0,
    ) -> None:
        self._positions = positions or []
        self._outstanding = outstanding or []
        self._recon = recon or {"status": "MATCHED", "shortfall": "0"}
        self._audit_count = audit_count

    def get_client_money_positions(self, as_of: datetime) -> list[ClientMoneyPosition]:
        return self._positions

    def get_outstanding_payments(self, as_of: datetime) -> list[dict]:
        return self._outstanding

    def get_reconciliation_summary(self, as_of: datetime) -> dict:
        return self._recon

    def get_audit_events_count(self, as_of: datetime) -> int:
        return self._audit_count


# ── ClickHouse repository (pragma: no cover — requires live CH) ────────────────


class ClickHouseResolutionRepository:  # pragma: no cover
    """
    Production repository — queries ClickHouse banxe database.
    Requires: CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_DB env vars.
    """

    def __init__(self) -> None:
        import os

        import clickhouse_driver  # type: ignore[import]

        self._client = clickhouse_driver.Client(
            host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
            port=int(os.environ.get("CLICKHOUSE_PORT", "9000")),
            database=os.environ.get("CLICKHOUSE_DB", "banxe"),
        )

    def get_client_money_positions(self, as_of: datetime) -> list[ClientMoneyPosition]:
        rows = self._client.execute(
            """
            SELECT customer_id, currency,
                   sum(amount) AS balance,
                   max(event_time) AS last_updated
            FROM banxe.safeguarding_events
            WHERE event_time <= %(as_of)s
              AND event_type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER_IN', 'TRANSFER_OUT')
            GROUP BY customer_id, currency
            HAVING balance > 0
            ORDER BY balance DESC
            """,
            {"as_of": as_of},
        )
        return [
            ClientMoneyPosition(
                customer_id=r[0],
                currency=r[1],
                balance=Decimal(str(r[2])),
                last_updated=r[3],
            )
            for r in rows
        ]

    def get_outstanding_payments(self, as_of: datetime) -> list[dict]:
        rows = self._client.execute(
            """
            SELECT payment_id, customer_id, amount, currency, status, created_at
            FROM banxe.payments
            WHERE created_at <= %(as_of)s
              AND status IN ('PENDING', 'PROCESSING')
            ORDER BY created_at
            """,
            {"as_of": as_of},
        )
        return [
            {
                "payment_id": r[0],
                "customer_id": r[1],
                "amount": str(r[2]),
                "currency": r[3],
                "status": r[4],
                "created_at": r[5].isoformat(),
            }
            for r in rows
        ]

    def get_reconciliation_summary(self, as_of: datetime) -> dict:
        rows = self._client.execute(
            """
            SELECT recon_status, midaz_balance, bank_balance, shortfall, event_time
            FROM banxe.safeguarding_events
            WHERE event_type = 'RECONCILIATION'
              AND event_time <= %(as_of)s
            ORDER BY event_time DESC
            LIMIT 1
            """,
            {"as_of": as_of},
        )
        if not rows:
            return {"status": "NO_RECON_ON_RECORD", "shortfall": "0"}
        r = rows[0]
        return {
            "status": r[0],
            "midaz_balance": str(r[1]),
            "bank_balance": str(r[2]),
            "shortfall": str(r[3]),
            "last_recon_at": r[4].isoformat(),
        }

    def get_audit_events_count(self, as_of: datetime) -> int:
        rows = self._client.execute(
            "SELECT count() FROM banxe.safeguarding_events WHERE event_time <= %(as_of)s",
            {"as_of": as_of},
        )
        return int(rows[0][0]) if rows else 0


# ── Pack builder ───────────────────────────────────────────────────────────────


class ResolutionPackBuilder:
    """
    Builds CASS 10A resolution pack from repository data.
    Satisfies FCA CASS 10A.3.1R (48h retrieval requirement).
    """

    def __init__(self, repo: ResolutionDataRepository, currency: str = "GBP") -> None:
        self._repo = repo
        self._currency = currency

    def build(self, as_of: datetime | None = None) -> ResolutionPack:
        """Build resolution pack snapshot. as_of defaults to now (UTC)."""
        as_of = as_of or datetime.now(UTC)
        generated_at = datetime.now(UTC)

        positions = self._repo.get_client_money_positions(as_of)
        outstanding = self._repo.get_outstanding_payments(as_of)
        recon = self._repo.get_reconciliation_summary(as_of)
        audit_count = self._repo.get_audit_events_count(as_of)

        total = sum(p.balance for p in positions)

        return ResolutionPack(
            generated_at=generated_at,
            as_of_date=as_of,
            total_client_money=total,
            currency=self._currency,
            positions=positions,
            outstanding_payments=outstanding,
            reconciliation_summary=recon,
            audit_events_count=audit_count,
        )

    def build_zip(self, pack: ResolutionPack) -> bytes:
        """
        Serialise resolution pack to ZIP bytes.
        ZIP contains: manifest.json, positions.csv, outstanding_payments.json

        FCA CASS 10A.3.2R: pack must contain client money statement.
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. JSON manifest
            zf.writestr("manifest.json", json.dumps(pack.to_manifest(), indent=2))

            # 2. Client money positions CSV
            pos_buf = io.StringIO()
            writer = csv.DictWriter(
                pos_buf,
                fieldnames=["customer_id", "currency", "balance", "last_updated", "account_id"],
            )
            writer.writeheader()
            for p in pack.positions:
                writer.writerow(
                    {
                        "customer_id": p.customer_id,
                        "currency": p.currency,
                        "balance": str(p.balance),
                        "last_updated": p.last_updated.isoformat(),
                        "account_id": p.account_id or "",
                    }
                )
            zf.writestr("positions.csv", pos_buf.getvalue())

            # 3. Outstanding payments JSON
            zf.writestr(
                "outstanding_payments.json",
                json.dumps(pack.outstanding_payments, indent=2),
            )

            # 4. Reconciliation summary
            zf.writestr(
                "reconciliation_summary.json",
                json.dumps(pack.reconciliation_summary, indent=2),
            )

        return buf.getvalue()
