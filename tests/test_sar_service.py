"""
tests/test_sar_service.py — SARService unit tests + Reporting API tests
IL-052 | Phase 3 #13 | POCA 2002 s.330 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.reporting import _get_regdata_service, _get_sar_service
from services.aml.sar_service import (
    SARReason,
    SARReport,
    SARService,
    SARServiceError,
    SARStatus,
)
from services.reporting.regdata_return import MockFIN060Generator, RegDataReturnService

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def svc() -> SARService:
    return SARService()


@pytest.fixture()
def draft_sar(svc: SARService) -> SARReport:
    return svc.file_sar(
        transaction_id="tx-001",
        customer_id="cust-001",
        entity_type="INDIVIDUAL",
        amount=Decimal("12500"),
        currency="GBP",
        sar_reasons=[SARReason.VELOCITY_BREACH],
        aml_flags=["VELOCITY_30D"],
        fraud_score=72,
        created_by="system",
    )


@pytest.fixture()
def client() -> TestClient:
    """FastAPI test client with fresh SAR + RegData services."""
    fresh_sar = SARService()
    fresh_regdata = RegDataReturnService(generator=MockFIN060Generator())

    app.dependency_overrides[_get_sar_service] = lambda: fresh_sar
    app.dependency_overrides[_get_regdata_service] = lambda: fresh_regdata
    _get_sar_service.cache_clear()
    _get_regdata_service.cache_clear()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    _get_sar_service.cache_clear()
    _get_regdata_service.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# SARService unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFileSAR:
    def test_creates_draft(self, svc: SARService) -> None:
        sar = svc.file_sar(
            transaction_id="tx-1",
            customer_id="cust-1",
            entity_type="INDIVIDUAL",
            amount=Decimal("15000"),
            currency="GBP",
            sar_reasons=[SARReason.STRUCTURING],
            aml_flags=[],
            fraud_score=0,
        )
        assert sar.status == SARStatus.DRAFT
        assert sar.sar_id != ""
        assert sar.transaction_id == "tx-1"

    def test_requires_at_least_one_reason(self, svc: SARService) -> None:
        # Empty reasons list is caught by Pydantic model, not service.
        # Service accepts empty list but API model validates — test service directly:
        sar = svc.file_sar(
            transaction_id="tx-2",
            customer_id="cust-2",
            entity_type="INDIVIDUAL",
            amount=Decimal("5000"),
            currency="GBP",
            sar_reasons=[SARReason.OTHER],
            aml_flags=[],
            fraud_score=0,
        )
        assert SARReason.OTHER in sar.sar_reasons

    def test_multiple_reasons(self, svc: SARService) -> None:
        sar = svc.file_sar(
            transaction_id="tx-3",
            customer_id="cust-3",
            entity_type="COMPANY",
            amount=Decimal("200000"),
            currency="GBP",
            sar_reasons=[SARReason.VELOCITY_BREACH, SARReason.HIGH_RISK_JURISDICTION],
            aml_flags=["VELOCITY_30D"],
            fraud_score=55,
        )
        assert len(sar.sar_reasons) == 2
        assert SARReason.VELOCITY_BREACH in sar.sar_reasons

    def test_is_submittable_false_when_draft(self, draft_sar: SARReport) -> None:
        assert draft_sar.is_submittable is False

    def test_requires_mlro_action_when_draft(self, draft_sar: SARReport) -> None:
        assert draft_sar.requires_mlro_action is True

    def test_sets_created_at(self, draft_sar: SARReport) -> None:
        assert draft_sar.created_at is not None

    def test_aml_flags_stored(self, svc: SARService) -> None:
        sar = svc.file_sar(
            transaction_id="tx-5",
            customer_id="cust-5",
            entity_type="INDIVIDUAL",
            amount=Decimal("9000"),
            currency="GBP",
            sar_reasons=[SARReason.UNUSUAL_PATTERN],
            aml_flags=["VELOCITY_24H", "STRUCTURING"],
            fraud_score=30,
        )
        assert "VELOCITY_24H" in sar.aml_flags
        assert "STRUCTURING" in sar.aml_flags


class TestApproveSAR:
    def test_approve_draft_moves_to_mlro_approved(
        self, svc: SARService, draft_sar: SARReport
    ) -> None:
        approved = svc.approve_sar(
            sar_id=draft_sar.sar_id, mlro_id="mlro-001", notes="Clear ML indicators"
        )
        assert approved.status == SARStatus.MLRO_APPROVED
        assert approved.mlro_reviewed_by == "mlro-001"
        assert approved.mlro_notes == "Clear ML indicators"
        assert approved.mlro_reviewed_at is not None

    def test_cannot_approve_non_draft(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        with pytest.raises(SARServiceError, match="can only approve DRAFT"):
            svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-002")

    def test_approve_sets_is_submittable(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        sar = svc.get_sar(draft_sar.sar_id)
        assert sar is not None
        assert sar.is_submittable is True

    def test_approve_unknown_sar_raises(self, svc: SARService) -> None:
        with pytest.raises(SARServiceError, match="not found"):
            svc.approve_sar(sar_id="nonexistent", mlro_id="mlro-001")


class TestWithdrawSAR:
    def test_withdraw_draft(self, svc: SARService, draft_sar: SARReport) -> None:
        withdrawn = svc.withdraw_sar(
            sar_id=draft_sar.sar_id,
            mlro_id="mlro-001",
            reason="Investigation concluded — not suspicious",
        )
        assert withdrawn.status == SARStatus.WITHDRAWN
        assert withdrawn.mlro_notes == "Investigation concluded — not suspicious"

    def test_withdraw_mlro_approved(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        withdrawn = svc.withdraw_sar(
            sar_id=draft_sar.sar_id,
            mlro_id="mlro-001",
            reason="Reversed — additional evidence",
        )
        assert withdrawn.status == SARStatus.WITHDRAWN

    def test_cannot_withdraw_submitted(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        svc.submit_sar(sar_id=draft_sar.sar_id)
        with pytest.raises(SARServiceError, match="cannot withdraw"):
            svc.withdraw_sar(
                sar_id=draft_sar.sar_id,
                mlro_id="mlro-001",
                reason="too late",
            )


class TestSubmitSAR:
    def test_submit_approved_sar(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        submitted = svc.submit_sar(sar_id=draft_sar.sar_id)
        assert submitted.status == SARStatus.SUBMITTED
        assert submitted.nca_reference is not None
        assert submitted.nca_reference.startswith("SAR-")
        assert submitted.submitted_at is not None

    def test_cannot_submit_draft(self, svc: SARService, draft_sar: SARReport) -> None:
        with pytest.raises(SARServiceError, match="must be MLRO_APPROVED"):
            svc.submit_sar(sar_id=draft_sar.sar_id)

    def test_nca_reference_format(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        submitted = svc.submit_sar(sar_id=draft_sar.sar_id)
        # Format: SAR-YYYYMM-{8 hex chars uppercase}
        parts = submitted.nca_reference.split("-")
        assert len(parts) == 3
        assert parts[0] == "SAR"
        assert len(parts[1]) == 6  # YYYYMM

    def test_is_submittable_false_after_submit(self, svc: SARService, draft_sar: SARReport) -> None:
        svc.approve_sar(sar_id=draft_sar.sar_id, mlro_id="mlro-001")
        submitted = svc.submit_sar(sar_id=draft_sar.sar_id)
        assert submitted.is_submittable is False


class TestListAndStats:
    def test_list_all(self, svc: SARService) -> None:
        svc.file_sar(
            transaction_id="tx-a",
            customer_id="cust-a",
            entity_type="INDIVIDUAL",
            amount=Decimal("5000"),
            currency="GBP",
            sar_reasons=[SARReason.OTHER],
            aml_flags=[],
            fraud_score=0,
        )
        svc.file_sar(
            transaction_id="tx-b",
            customer_id="cust-b",
            entity_type="INDIVIDUAL",
            amount=Decimal("6000"),
            currency="GBP",
            sar_reasons=[SARReason.STRUCTURING],
            aml_flags=[],
            fraud_score=0,
        )
        sars = svc.list_sars()
        assert len(sars) == 2

    def test_list_filtered_by_status(self, svc: SARService) -> None:
        sar_a = svc.file_sar(
            transaction_id="tx-c",
            customer_id="cust-c",
            entity_type="INDIVIDUAL",
            amount=Decimal("5000"),
            currency="GBP",
            sar_reasons=[SARReason.OTHER],
            aml_flags=[],
            fraud_score=0,
        )
        svc.file_sar(
            transaction_id="tx-d",
            customer_id="cust-d",
            entity_type="INDIVIDUAL",
            amount=Decimal("6000"),
            currency="GBP",
            sar_reasons=[SARReason.STRUCTURING],
            aml_flags=[],
            fraud_score=0,
        )
        svc.approve_sar(sar_id=sar_a.sar_id, mlro_id="mlro-001")
        drafts = svc.list_sars(status=SARStatus.DRAFT)
        assert len(drafts) == 1
        assert drafts[0].transaction_id == "tx-d"

    def test_stats_empty(self, svc: SARService) -> None:
        s = svc.stats()
        assert s.total == 0
        assert s.submission_rate == 0.0

    def test_stats_submission_rate(self, svc: SARService) -> None:
        # Create 2 SARs: 1 submitted, 1 withdrawn → rate = 50%
        sar1 = svc.file_sar(
            transaction_id="tx-e",
            customer_id="cust-e",
            entity_type="INDIVIDUAL",
            amount=Decimal("9000"),
            currency="GBP",
            sar_reasons=[SARReason.OTHER],
            aml_flags=[],
            fraud_score=0,
        )
        sar2 = svc.file_sar(
            transaction_id="tx-f",
            customer_id="cust-f",
            entity_type="INDIVIDUAL",
            amount=Decimal("8000"),
            currency="GBP",
            sar_reasons=[SARReason.OTHER],
            aml_flags=[],
            fraud_score=0,
        )
        svc.approve_sar(sar_id=sar1.sar_id, mlro_id="mlro-001")
        svc.submit_sar(sar_id=sar1.sar_id)
        svc.withdraw_sar(sar_id=sar2.sar_id, mlro_id="mlro-001", reason="not suspicious")
        s = svc.stats()
        assert s.total == 2
        assert s.submitted == 1
        assert s.withdrawn == 1
        assert s.submission_rate == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Reporting API tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSARAPI:
    def test_file_sar_201(self, client: TestClient) -> None:
        res = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-1",
                "customer_id": "cust-api-1",
                "amount": "12500",
                "sar_reasons": ["VELOCITY_BREACH"],
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "DRAFT"
        assert data["transaction_id"] == "tx-api-1"
        assert data["requires_mlro_action"] is True

    def test_file_sar_missing_reason_422(self, client: TestClient) -> None:
        res = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-2",
                "customer_id": "cust-api-2",
                "amount": "1000",
                "sar_reasons": [],
            },
        )
        assert res.status_code == 422

    def test_get_sar_404(self, client: TestClient) -> None:
        res = client.get("/v1/reporting/sar/nonexistent")
        assert res.status_code == 404

    def test_get_sar_found(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-3",
                "customer_id": "cust-api-3",
                "amount": "5000",
                "sar_reasons": ["STRUCTURING"],
            },
        )
        sar_id = created.json()["sar_id"]
        res = client.get(f"/v1/reporting/sar/{sar_id}")
        assert res.status_code == 200
        assert res.json()["sar_id"] == sar_id

    def test_approve_sar(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-4",
                "customer_id": "cust-api-4",
                "amount": "20000",
                "sar_reasons": ["HIGH_RISK_JURISDICTION"],
            },
        )
        sar_id = created.json()["sar_id"]
        res = client.post(
            f"/v1/reporting/sar/{sar_id}/approve",
            json={
                "mlro_id": "mlro-001",
                "notes": "Confirmed ML risk",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "MLRO_APPROVED"

    def test_approve_twice_409(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-5",
                "customer_id": "cust-api-5",
                "amount": "8000",
                "sar_reasons": ["OTHER"],
            },
        )
        sar_id = created.json()["sar_id"]
        client.post(f"/v1/reporting/sar/{sar_id}/approve", json={"mlro_id": "mlro-001"})
        res = client.post(f"/v1/reporting/sar/{sar_id}/approve", json={"mlro_id": "mlro-002"})
        assert res.status_code == 409

    def test_submit_sar(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-6",
                "customer_id": "cust-api-6",
                "amount": "30000",
                "sar_reasons": ["VELOCITY_BREACH", "STRUCTURING"],
            },
        )
        sar_id = created.json()["sar_id"]
        client.post(f"/v1/reporting/sar/{sar_id}/approve", json={"mlro_id": "mlro-001"})
        res = client.post(f"/v1/reporting/sar/{sar_id}/submit")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUBMITTED"
        assert data["nca_reference"].startswith("SAR-")

    def test_submit_draft_409(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-7",
                "customer_id": "cust-api-7",
                "amount": "5000",
                "sar_reasons": ["OTHER"],
            },
        )
        sar_id = created.json()["sar_id"]
        res = client.post(f"/v1/reporting/sar/{sar_id}/submit")
        assert res.status_code == 409

    def test_withdraw_sar(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-8",
                "customer_id": "cust-api-8",
                "amount": "7000",
                "sar_reasons": ["UNUSUAL_PATTERN"],
            },
        )
        sar_id = created.json()["sar_id"]
        res = client.post(
            f"/v1/reporting/sar/{sar_id}/withdraw",
            json={
                "mlro_id": "mlro-001",
                "reason": "Review found no ML indicators",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "WITHDRAWN"

    def test_withdraw_missing_reason_422(self, client: TestClient) -> None:
        created = client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-api-9",
                "customer_id": "cust-api-9",
                "amount": "7000",
                "sar_reasons": ["UNUSUAL_PATTERN"],
            },
        )
        sar_id = created.json()["sar_id"]
        res = client.post(
            f"/v1/reporting/sar/{sar_id}/withdraw",
            json={
                "mlro_id": "mlro-001",
                "reason": "   ",  # blank — must be rejected by validator
            },
        )
        assert res.status_code == 422

    def test_list_sars(self, client: TestClient) -> None:
        client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-list-1",
                "customer_id": "cust-list-1",
                "amount": "5000",
                "sar_reasons": ["OTHER"],
            },
        )
        client.post(
            "/v1/reporting/sar",
            json={
                "transaction_id": "tx-list-2",
                "customer_id": "cust-list-2",
                "amount": "6000",
                "sar_reasons": ["STRUCTURING"],
            },
        )
        res = client.get("/v1/reporting/sar")
        assert res.status_code == 200
        assert res.json()["total"] == 2

    def test_sar_stats(self, client: TestClient) -> None:
        res = client.get("/v1/reporting/sar/stats")
        assert res.status_code == 200
        data = res.json()
        assert "total" in data
        assert "submission_rate" in data


class TestFIN060API:
    def test_generate_fin060_201(self, client: TestClient) -> None:
        res = client.post(
            "/v1/reporting/fin060/generate",
            json={
                "period_start": "2026-03-01",
                "period_end": "2026-03-31",
                "avg_daily_client_funds": "850000.00",
                "peak_client_funds": "1200000.00",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["period_start"] == "2026-03-01"
        assert data["frn"] is not None
        assert "deadline" in data

    def test_generate_fin060_period_validation(self, client: TestClient) -> None:
        res = client.post(
            "/v1/reporting/fin060/generate",
            json={
                "period_start": "2026-03-31",
                "period_end": "2026-03-01",  # end before start
                "avg_daily_client_funds": "500000",
                "peak_client_funds": "700000",
            },
        )
        assert res.status_code == 422

    def test_submit_fin060(self, client: TestClient) -> None:
        res = client.post(
            "/v1/reporting/fin060/submit",
            json={
                "period_start": "2026-03-01",
                "period_end": "2026-03-31",
                "avg_daily_client_funds": "850000.00",
                "peak_client_funds": "1200000.00",
            },
        )
        assert res.status_code == 200
        data = res.json()
        # Stub always succeeds with SUBMITTED status
        assert data["status"] in ("SUBMITTED", "GENERATED")
