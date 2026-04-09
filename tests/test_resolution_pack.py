"""
test_resolution_pack.py — Tests for CASS 10A Resolution Pack Builder (S6-14)
FCA CASS 10A.3.1R | banxe-emi-stack
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.resolution.resolution_pack import (
    ClientMoneyPosition,
    InMemoryResolutionRepository,
    ResolutionPackBuilder,
)


def _make_position(cid: str, balance: str, currency: str = "GBP") -> ClientMoneyPosition:
    return ClientMoneyPosition(
        customer_id=cid,
        currency=currency,
        balance=Decimal(balance),
        last_updated=datetime.now(UTC),
    )


@pytest.fixture
def positions():
    return [
        _make_position("cust-001", "10000.00"),
        _make_position("cust-002", "5000.50"),
        _make_position("cust-003", "250.00"),
    ]


@pytest.fixture
def repo(positions):
    return InMemoryResolutionRepository(
        positions=positions,
        outstanding=[
            {
                "payment_id": "pay-001",
                "customer_id": "cust-001",
                "amount": "500.00",
                "currency": "GBP",
                "status": "PENDING",
                "created_at": "2026-04-08T10:00:00Z",
            },
        ],
        recon={"status": "MATCHED", "shortfall": "0", "midaz_balance": "15250.50"},
        audit_count=4200,
    )


@pytest.fixture
def builder(repo):
    return ResolutionPackBuilder(repo, currency="GBP")


class TestPackBuild:
    def test_total_client_money(self, builder):
        pack = builder.build()
        assert pack.total_client_money == Decimal("15250.50")

    def test_position_count(self, builder, positions):
        pack = builder.build()
        assert len(pack.positions) == len(positions)

    def test_outstanding_payments(self, builder):
        pack = builder.build()
        assert len(pack.outstanding_payments) == 1
        assert pack.outstanding_payments[0]["status"] == "PENDING"

    def test_reconciliation_summary(self, builder):
        pack = builder.build()
        assert pack.reconciliation_summary["status"] == "MATCHED"

    def test_audit_events_count(self, builder):
        pack = builder.build()
        assert pack.audit_events_count == 4200

    def test_fca_rule_set(self, builder):
        pack = builder.build()
        assert pack.fca_rule == "CASS 10A.3.1R"

    def test_currency_set(self, builder):
        pack = builder.build()
        assert pack.currency == "GBP"

    def test_generated_at_utc(self, builder):
        pack = builder.build()
        assert pack.generated_at.tzinfo is not None


class TestPackManifest:
    def test_manifest_keys(self, builder):
        pack = builder.build()
        manifest = pack.to_manifest()
        assert "generated_at" in manifest
        assert "total_client_money" in manifest
        assert "position_count" in manifest
        assert "fca_rule" in manifest

    def test_manifest_total_is_string(self, builder):
        pack = builder.build()
        manifest = pack.to_manifest()
        assert isinstance(manifest["total_client_money"], str)

    def test_manifest_position_count(self, builder, positions):
        pack = builder.build()
        manifest = pack.to_manifest()
        assert manifest["position_count"] == len(positions)


class TestEmptyRepo:
    def test_empty_positions(self):
        repo = InMemoryResolutionRepository(positions=[], audit_count=0)
        builder = ResolutionPackBuilder(repo)
        pack = builder.build()
        assert pack.total_client_money == Decimal("0")
        assert pack.positions == []


class TestZipExport:
    def test_zip_returns_bytes(self, builder):
        pack = builder.build()
        data = builder.build_zip(pack)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_zip_contains_required_files(self, builder):
        pack = builder.build()
        data = builder.build_zip(pack)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
        assert "manifest.json" in names
        assert "positions.csv" in names
        assert "outstanding_payments.json" in names
        assert "reconciliation_summary.json" in names

    def test_zip_manifest_valid_json(self, builder):
        pack = builder.build()
        data = builder.build_zip(pack)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["fca_rule"] == "CASS 10A.3.1R"
        assert manifest["position_count"] == 3

    def test_zip_positions_csv_has_rows(self, builder):
        pack = builder.build()
        data = builder.build_zip(pack)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csv_content = zf.read("positions.csv").decode()
        lines = [ln for ln in csv_content.strip().split("\n") if ln]
        assert len(lines) == 4  # header + 3 positions

    def test_zip_outstanding_payments_json(self, builder):
        pack = builder.build()
        data = builder.build_zip(pack)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            payments = json.loads(zf.read("outstanding_payments.json"))
        assert len(payments) == 1
        assert payments[0]["payment_id"] == "pay-001"


class TestSlaCompliance:
    def test_build_is_fast(self, builder):
        """CASS 10A.3.1R: pack must be retrievable within 48h — on-demand generation."""
        import time

        t0 = time.monotonic()
        builder.build()
        elapsed_s = time.monotonic() - t0
        assert elapsed_s < 1.0  # on-demand generation must be sub-second
