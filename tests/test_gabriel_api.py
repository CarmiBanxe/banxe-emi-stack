"""
tests/test_gabriel_api.py
K-gabriel API layer tests (IL-CBS-GABRIEL-API-2026-06-26).

Tests governor extensions (list/get_by_id/approve/reject) and
FastAPI router endpoints via TestClient.

Coverage:
  - ReturnsGovernor.list_records / get_by_id
  - ReturnsGovernor.approve — happy path, not-found, validation-blocked
  - ReturnsGovernor.reject — happy path, not-found
  - GET /v1/gabriel/returns (empty and populated)
  - GET /v1/gabriel/returns/{id} (found / not-found)
  - POST /v1/gabriel/returns (create draft)
  - POST /v1/gabriel/returns/{id}/approve (happy + errors)
  - POST /v1/gabriel/returns/{id}/reject (happy + not-found)
  - GET /v1/gabriel/deadline/{type}/{period}
  - 422 on unknown return_type
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from services.gabriel.gabriel_models import (
    GabrielReturnStatus,
    GabrielReturnType,
    InMemoryGabrielAuditPort,
    InMemoryGabrielSubmissionPort,
)
from services.gabriel.returns_governor import ReturnsGovernor

# ── Fixtures ──────────────────────────────────────────────────────────────────

PERIOD_MAY = "2026-05"
PERIOD_BREACH = "2026-06-20"


def _governor_with_audit() -> tuple[ReturnsGovernor, InMemoryGabrielAuditPort]:
    audit = InMemoryGabrielAuditPort()
    return ReturnsGovernor(audit=audit), audit


def _governor() -> ReturnsGovernor:
    return ReturnsGovernor(audit=InMemoryGabrielAuditPort())


# ── ReturnsGovernor: list_records / get_by_id ─────────────────────────────────


class TestGovernorQuery:
    def test_list_empty_initially(self) -> None:
        gov = _governor()
        assert gov.list_records() == []

    def test_list_returns_all_records(self) -> None:
        gov = _governor()
        gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.get_or_create(GabrielReturnType.BREACH_REPORT, PERIOD_BREACH)
        assert len(gov.list_records()) == 2

    def test_get_by_id_found(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        found = gov.get_by_id(record.submission_id)
        assert found is not None
        assert found.submission_id == record.submission_id

    def test_get_by_id_not_found_returns_none(self) -> None:
        gov = _governor()
        assert gov.get_by_id("nonexistent-id") is None

    def test_list_idempotent_no_duplicates(self) -> None:
        gov = _governor()
        gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)  # same key
        assert len(gov.list_records()) == 1


# ── ReturnsGovernor.approve ───────────────────────────────────────────────────


class TestGovernorApprove:
    def test_approve_happy_path_returns_submitted(self) -> None:
        gov, audit = _governor_with_audit()
        port = InMemoryGabrielSubmissionPort()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        submitted = gov.approve(record.submission_id, "MLRO-Alice", port)
        assert submitted.status == GabrielReturnStatus.SUBMITTED
        assert submitted.submitted_at is not None
        assert submitted.submission_ref is not None

    def test_approve_audit_action_is_approved_submitted(self) -> None:
        gov, audit = _governor_with_audit()
        port = InMemoryGabrielSubmissionPort()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.approve(record.submission_id, "MLRO-Alice", port)
        actions = [e.action for e in audit.entries]
        assert "APPROVED_SUBMITTED" in actions

    def test_approve_not_found_raises_key_error(self) -> None:
        gov = _governor()
        port = InMemoryGabrielSubmissionPort()
        with pytest.raises(KeyError):
            gov.approve("bad-id", "MLRO-Alice", port)

    def test_approve_already_submitted_raises_value_error(self) -> None:
        gov = _governor()
        port = InMemoryGabrielSubmissionPort()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.approve(record.submission_id, "MLRO-Alice", port)  # first submit
        refetched = gov.get_by_id(record.submission_id)
        assert refetched is not None
        with pytest.raises(ValueError):
            gov.approve(refetched.submission_id, "MLRO-Alice", port)

    def test_approve_updates_record_in_governor(self) -> None:
        gov = _governor()
        port = InMemoryGabrielSubmissionPort()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.approve(record.submission_id, "MLRO-Alice", port)
        updated = gov.get_by_id(record.submission_id)
        assert updated is not None
        assert updated.status == GabrielReturnStatus.SUBMITTED

    def test_approve_delegates_to_port(self) -> None:
        gov = _governor()
        port = InMemoryGabrielSubmissionPort()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.approve(record.submission_id, "MLRO-Alice", port)
        assert len(port.submitted) == 1
        assert port.submitted[0].submission_id == record.submission_id


# ── ReturnsGovernor.reject ────────────────────────────────────────────────────


class TestGovernorReject:
    def test_reject_happy_path_returns_rejected(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        rejected = gov.reject(record.submission_id, "MLRO-Alice", "Incorrect period")
        assert rejected.status == GabrielReturnStatus.REJECTED

    def test_reject_audit_action_is_rejected(self) -> None:
        gov, audit = _governor_with_audit()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.reject(record.submission_id, "MLRO-Alice", "Wrong data")
        actions = [e.action for e in audit.entries]
        assert "REJECTED" in actions

    def test_reject_not_found_raises_key_error(self) -> None:
        gov = _governor()
        with pytest.raises(KeyError):
            gov.reject("bad-id", "MLRO-Alice", "reason")

    def test_reject_updates_record_in_governor(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        gov.reject(record.submission_id, "MLRO-Alice", "reason")
        updated = gov.get_by_id(record.submission_id)
        assert updated is not None
        assert updated.status == GabrielReturnStatus.REJECTED


# ── API layer via TestClient ───────────────────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    """Fresh governor state per test — reset module singleton."""
    from api.main import app
    import api.routers.gabriel as gabriel_router

    gabriel_router._governor = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
    gabriel_router._submission_port = InMemoryGabrielSubmissionPort()
    return TestClient(app)


class TestGabrielApiListCreate:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/v1/gabriel/returns")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_draft_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/gabriel/returns",
            json={"return_type": "FIN060", "return_period": PERIOD_MAY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["return_type"] == "FIN060"
        assert data["status"] == "DRAFT"
        assert data["idempotency_key"] == "FIN060:2026-05"

    def test_create_draft_idempotent(self, client: TestClient) -> None:
        payload = {"return_type": "FIN060", "return_period": PERIOD_MAY}
        r1 = client.post("/v1/gabriel/returns", json=payload)
        r2 = client.post("/v1/gabriel/returns", json=payload)
        assert r1.json()["submission_id"] == r2.json()["submission_id"]

    def test_list_shows_created_record(self, client: TestClient) -> None:
        client.post(
            "/v1/gabriel/returns",
            json={"return_type": "FIN060", "return_period": PERIOD_MAY},
        )
        resp = client.get("/v1/gabriel/returns")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_create_unknown_return_type_422(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/gabriel/returns",
            json={"return_type": "BOGUS_TYPE", "return_period": PERIOD_MAY},
        )
        assert resp.status_code == 422


class TestGabrielApiGetById:
    def test_get_found(self, client: TestClient) -> None:
        created = client.post(
            "/v1/gabriel/returns",
            json={"return_type": "FIN060", "return_period": PERIOD_MAY},
        ).json()
        resp = client.get(f"/v1/gabriel/returns/{created['submission_id']}")
        assert resp.status_code == 200
        assert resp.json()["submission_id"] == created["submission_id"]

    def test_get_not_found_404(self, client: TestClient) -> None:
        resp = client.get("/v1/gabriel/returns/nonexistent-id")
        assert resp.status_code == 404


class TestGabrielApiApprove:
    def test_approve_returns_submitted(self, client: TestClient) -> None:
        created = client.post(
            "/v1/gabriel/returns",
            json={"return_type": "FIN060", "return_period": PERIOD_MAY},
        ).json()
        resp = client.post(
            f"/v1/gabriel/returns/{created['submission_id']}/approve",
            json={"approved_by": "MLRO-Alice"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUBMITTED"
        assert data["submitted_at"] is not None
        assert data["submission_ref"] is not None

    def test_approve_not_found_404(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/gabriel/returns/bad-id/approve",
            json={"approved_by": "MLRO-Alice"},
        )
        assert resp.status_code == 404

    def test_approve_already_submitted_422(self, client: TestClient) -> None:
        created = client.post(
            "/v1/gabriel/returns",
            json={"return_type": "FIN060", "return_period": PERIOD_MAY},
        ).json()
        sid = created["submission_id"]
        client.post(f"/v1/gabriel/returns/{sid}/approve", json={"approved_by": "MLRO"})
        resp = client.post(
            f"/v1/gabriel/returns/{sid}/approve", json={"approved_by": "MLRO"}
        )
        assert resp.status_code == 422


class TestGabrielApiReject:
    def test_reject_returns_rejected_status(self, client: TestClient) -> None:
        created = client.post(
            "/v1/gabriel/returns",
            json={"return_type": "FIN060", "return_period": PERIOD_MAY},
        ).json()
        resp = client.post(
            f"/v1/gabriel/returns/{created['submission_id']}/reject",
            json={"rejected_by": "MLRO-Bob", "reason": "Incorrect amounts"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    def test_reject_not_found_404(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/gabriel/returns/bad-id/reject",
            json={"rejected_by": "MLRO-Bob", "reason": "reason"},
        )
        assert resp.status_code == 404


class TestGabrielApiDeadline:
    def test_deadline_fin060_returns_15th_next_month(self, client: TestClient) -> None:
        resp = client.get("/v1/gabriel/deadline/FIN060/2026-05")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deadline_date"] == "2026-06-15"
        assert data["return_type"] == "FIN060"

    def test_deadline_breach_report_two_days(self, client: TestClient) -> None:
        resp = client.get("/v1/gabriel/deadline/BREACH_REPORT/2026-06-20")
        assert resp.status_code == 200
        assert resp.json()["deadline_date"] == "2026-06-22"

    def test_deadline_unknown_type_422(self, client: TestClient) -> None:
        resp = client.get("/v1/gabriel/deadline/BOGUS/2026-05")
        assert resp.status_code == 422
