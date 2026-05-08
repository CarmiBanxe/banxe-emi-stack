"""
sumsub_http_stub.py — Production wiring stub for KYC via SumSub REST API.

Satisfies KYCWorkflowPort structurally but raises NotImplementedError on all
network-touching methods. Marks the production integration surface for Wave D.

Canon: ADR-025 §15-16 + KYCWorkflowPort FROZEN (PORT-CONTRACTS-FREEZE-2026-05-08)
"""

from __future__ import annotations

from services.kyc.kyc_port import (
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)


class SumsubHttpStub:
    """
    Production stub: KYC workflow via SumSub REST API (HMAC-signed).

    Requirements for production implementation:
      - Package dep: httpx>=0.27 (already in pyproject.toml)
      - Env vars: SUMSUB_APP_TOKEN, SUMSUB_SECRET_KEY, SUMSUB_BASE_URL
      - HMAC-SHA256 signature per SumSub API v1 spec (X-App-Token + X-App-Access-Sig headers)
      - Integration tests: run against SumSub sandbox applicant fixtures
      - Implement create_workflow() via POST /resources/applicants + levelName query param
      - Implement submit_documents() via POST /resources/applicants/{applicantId}/info/idDoc
      - Implement approve_edd() via POST /resources/applicants/{applicantId}/status/approve
      - Implement reject_workflow() via POST /resources/applicants/{applicantId}/status/reject
      - Wire webhook handler for applicantReviewed events (I-27 HITL gate required)
      - I-24: All transitions must emit SumSubAuditRecord before returning result

    Implement in a separate PR tagged [IL-KYC-PROD-01].
    """

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        raise NotImplementedError(
            "SumsubHttpStub.create_workflow: not implemented. "
            "Requires SUMSUB_APP_TOKEN + SUMSUB_SECRET_KEY + SUMSUB_BASE_URL env vars. "
            "Implement in a dedicated production PR with SumSub sandbox integration tests."
        )

    def get_workflow(self, workflow_id: str) -> KYCWorkflowResult | None:
        raise NotImplementedError(
            "SumsubHttpStub.get_workflow: not implemented. "
            "Requires SUMSUB_APP_TOKEN + SUMSUB_SECRET_KEY + SUMSUB_BASE_URL env vars."
        )

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        raise NotImplementedError(
            "SumsubHttpStub.submit_documents: not implemented. "
            "Requires SUMSUB_APP_TOKEN + SUMSUB_SECRET_KEY + SUMSUB_BASE_URL env vars."
        )

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        raise NotImplementedError(
            "SumsubHttpStub.approve_edd: not implemented. "
            "Requires SUMSUB_APP_TOKEN + SUMSUB_SECRET_KEY + SUMSUB_BASE_URL env vars. "
            "I-27: MLRO human approval gate must be enforced before calling this method."
        )

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        raise NotImplementedError(
            "SumsubHttpStub.reject_workflow: not implemented. "
            "Requires SUMSUB_APP_TOKEN + SUMSUB_SECRET_KEY + SUMSUB_BASE_URL env vars."
        )

    def health(self) -> bool:
        raise NotImplementedError(
            "SumsubHttpStub.health: not implemented. "
            "Production: GET /resources/status against SumSub API with timeout guard."
        )
