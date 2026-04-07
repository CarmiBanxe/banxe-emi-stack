"""
mock_kyc_workflow.py — In-memory Mock KYC Workflow Engine (S5-13 / Ballerine)
FCA MLR 2017 | banxe-emi-stack

WHY THIS EXISTS
---------------
Ballerine requires a running instance. MockKYCWorkflow provides a deterministic
in-memory state machine that:
  - Triggers EDD automatically for PEPs, high-risk jurisdictions, large volumes
  - Enforces MLRO sign-off for EDD cases (FCA MLR 2017 §33)
  - Rejects on hard-block jurisdictions (INVARIANTS.md I-02)
  - Expires workflows after 30 days

State machine transitions:
  PENDING → DOCUMENT_REVIEW  (submit_documents called)
  DOCUMENT_REVIEW → RISK_ASSESSMENT  (auto, after document acceptance)
  RISK_ASSESSMENT → EDD_REQUIRED    (if EDD trigger present)
  RISK_ASSESSMENT → APPROVED         (clean, low-risk)
  RISK_ASSESSMENT → REJECTED         (sanctions / high risk)
  EDD_REQUIRED → MLRO_REVIEW         (auto, referral to MLRO)
  MLRO_REVIEW → APPROVED             (mlro approve_edd)
  MLRO_REVIEW → REJECTED             (mlro reject)
  Any → EXPIRED                      (TTL elapsed)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from services.kyc.kyc_port import (
    KYCStatus,
    KYCWorkflowPort,
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)

# FCA MLR 2017: CDD must be completed; 30 days is the standard operational TTL
_WORKFLOW_TTL_DAYS = 30

# INVARIANTS.md I-02 — hard-block jurisdictions
_BLOCKED_COUNTRIES = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE"}

# I-03 — high-risk jurisdictions (FATF greylist) → EDD required
_HIGH_RISK_COUNTRIES = {
    "SY", "IQ", "LB", "YE", "HT", "ML", "DZ", "AO", "BO", "VG",
    "CM", "CI", "CD", "KE", "LA", "MC", "NA", "NP", "SS", "TT",
    "VU", "BG", "VN",
}

# I-04 — EDD threshold
_EDD_VOLUME_THRESHOLD = Decimal("10000")


class MockKYCWorkflow:
    """
    Deterministic in-memory KYC state machine.
    Satisfies KYCWorkflowPort. No external dependencies.
    """

    def __init__(self) -> None:
        self._workflows: dict[str, KYCWorkflowResult] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """Create new KYC workflow and run initial risk check."""
        now = self._now()
        workflow_id = f"kyc-{uuid.uuid4().hex[:12]}"

        result = KYCWorkflowResult(
            workflow_id=workflow_id,
            customer_id=request.customer_id,
            status=KYCStatus.PENDING,
            kyc_type=request.kyc_type,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=_WORKFLOW_TTL_DAYS),
        )

        # Hard-block check (I-02)
        if request.nationality in _BLOCKED_COUNTRIES or \
                request.country_of_residence in _BLOCKED_COUNTRIES:
            result.status = KYCStatus.REJECTED
            result.rejection_reason = RejectionReason.HIGH_RISK_JURISDICTION
            result.risk_score = 100
            result.notes.append(
                f"Blocked jurisdiction detected: nationality={request.nationality} "
                f"residence={request.country_of_residence}"
            )
            self._workflows[workflow_id] = result
            return result

        # EDD triggers (I-03, I-04, MLR 2017 §33)
        edd_triggers = []
        if request.is_pep:
            edd_triggers.append("PEP status")
        if request.nationality in _HIGH_RISK_COUNTRIES or \
                request.country_of_residence in _HIGH_RISK_COUNTRIES:
            edd_triggers.append(
                f"High-risk jurisdiction: {request.nationality or request.country_of_residence}"
            )
        if request.expected_transaction_volume >= _EDD_VOLUME_THRESHOLD:
            edd_triggers.append(
                f"Expected volume £{request.expected_transaction_volume:,.0f} ≥ £10,000 (I-04)"
            )

        result.edd_required = bool(edd_triggers)
        if edd_triggers:
            result.notes.extend(edd_triggers)

        self._workflows[workflow_id] = result
        return result

    def get_workflow(self, workflow_id: str) -> Optional[KYCWorkflowResult]:
        result = self._workflows.get(workflow_id)
        if result is None:
            return None
        # Check TTL
        if not result.is_terminal and self._now() > result.expires_at:
            result.status = KYCStatus.EXPIRED
            result.updated_at = self._now()
        return result

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        """Advance PENDING → DOCUMENT_REVIEW → RISK_ASSESSMENT (→ EDD/APPROVED/REJECTED)."""
        result = self._workflows.get(workflow_id)
        if result is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        if result.is_terminal:
            raise ValueError(f"Workflow {workflow_id} is in terminal state {result.status}")
        if not document_ids:
            raise ValueError("At least one document_id required")

        result.updated_at = self._now()
        result.notes.append(f"Documents submitted: {', '.join(document_ids)}")
        result.status = KYCStatus.DOCUMENT_REVIEW

        # Auto-advance to RISK_ASSESSMENT (mock: instant)
        result.status = KYCStatus.RISK_ASSESSMENT

        # Risk scoring (simplified)
        score = 10  # base
        if result.edd_required:
            score += 40
        result.risk_score = min(score, 100)

        # Terminal decision
        if result.edd_required:
            result.status = KYCStatus.EDD_REQUIRED
            result.status = KYCStatus.MLRO_REVIEW  # auto-refer to MLRO
            result.notes.append("Case referred to MLRO for EDD sign-off (FCA MLR 2017 §33)")
        elif score >= 70:
            result.status = KYCStatus.REJECTED
            result.rejection_reason = RejectionReason.RISK_SCORE_TOO_HIGH
        else:
            result.status = KYCStatus.APPROVED
            result.notes.append("KYC APPROVED — CDD complete (FCA MLR 2017 §18)")

        return result

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """MLRO signs off EDD → APPROVED. Only valid in MLRO_REVIEW state."""
        result = self._workflows.get(workflow_id)
        if result is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        if result.status != KYCStatus.MLRO_REVIEW:
            raise ValueError(
                f"approve_edd only valid in MLRO_REVIEW state, current: {result.status}"
            )
        result.status = KYCStatus.APPROVED
        result.mlro_sign_off = True
        result.updated_at = self._now()
        result.notes.append(
            f"EDD approved by MLRO: {mlro_user_id} at {result.updated_at.isoformat()}"
        )
        return result

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        """Reject workflow at any non-terminal stage."""
        result = self._workflows.get(workflow_id)
        if result is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        if result.is_terminal:
            raise ValueError(f"Workflow {workflow_id} already in terminal state {result.status}")
        result.status = KYCStatus.REJECTED
        result.rejection_reason = reason
        result.updated_at = self._now()
        result.notes.append(f"Rejected: {reason.value}")
        return result

    def health(self) -> bool:
        return True


class BallerineAdapter:  # pragma: no cover
    """
    Live Ballerine KYC orchestration adapter (stub).
    STATUS: STUB — requires Ballerine deployment.

    Deploy: docker compose -f infra/ballerine/docker-compose.yml up
    Docs: https://docs.ballerine.com
    """

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        raise NotImplementedError(
            "BallerineAdapter not implemented. "
            "Deploy Ballerine and configure BALLERINE_URL. "
            "Use KYC_ADAPTER=mock for development."
        )

    def get_workflow(self, workflow_id: str) -> Optional[KYCWorkflowResult]:
        raise NotImplementedError

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        raise NotImplementedError

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        raise NotImplementedError

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        raise NotImplementedError

    def health(self) -> bool:
        return False


def get_kyc_adapter() -> KYCWorkflowPort:
    """Factory: KYC_ADAPTER=mock (default) | ballerine."""
    import os
    adapter = os.environ.get("KYC_ADAPTER", "mock").lower()
    if adapter == "ballerine":
        return BallerineAdapter()
    return MockKYCWorkflow()
