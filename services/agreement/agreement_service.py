"""
agreement_service.py — Agreement Service (In-Memory + DocuSign stub)
S17-02: T&C generation per product + e-sig + version history
FCA COBS 6, eIDAS Reg.910/2014
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import logging
import uuid

from .agreement_port import (
    Agreement,
    AgreementError,
    AgreementStatus,
    CreateAgreementRequest,
    ProductType,
    SignAgreementRequest,
    SignatureStatus,
    TermsVersion,
)

logger = logging.getLogger(__name__)

# ── T&C templates (Phase 1: static; Phase 2: DB-backed) ───────────────────────

_TC_TEMPLATES: dict[ProductType, str] = {
    ProductType.EMONEY_ACCOUNT: (
        "Banxe E-Money Account Terms and Conditions v1.0.0. "
        "Banxe is authorised by the FCA as an Electronic Money Institution. "
        "Your funds are safeguarded under FCA CASS 7."
    ),
    ProductType.FX_SERVICE: (
        "Banxe FX Service Terms and Conditions v1.0.0. "
        "FX transactions are subject to market risk. "
        "FCA COBS 6 product disclosure applies."
    ),
    ProductType.SAVINGS_ACCOUNT: (
        "Banxe Savings Account Terms and Conditions v1.0.0. "
        "Interest rates subject to change. "
        "FCA COBS 9A suitability assessment required."
    ),
    ProductType.PAYMENT_SERVICES: (
        "Banxe Payment Services Terms and Conditions v1.0.0. "
        "PSR 2017 and FCA PS7/24 apply. "
        "Strong Customer Authentication required for payments >£30."
    ),
}

_CURRENT_VERSIONS: dict[ProductType, str] = {
    ProductType.EMONEY_ACCOUNT: "1.0.0",
    ProductType.FX_SERVICE: "1.0.0",
    ProductType.SAVINGS_ACCOUNT: "1.0.0",
    ProductType.PAYMENT_SERVICES: "1.0.0",
}


def _content_hash(product_type: ProductType, version: str) -> str:
    content = _TC_TEMPLATES.get(product_type, "") + version
    return hashlib.sha256(content.encode()).hexdigest()


# ── In-memory service ──────────────────────────────────────────────────────────


class InMemoryAgreementService:
    """
    In-memory Agreement service for tests + development.
    Enforces eIDAS e-sig workflow (PENDING → SIGNED) and version history.
    """

    def __init__(self) -> None:
        self._agreements: dict[str, Agreement] = {}

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def create_agreement(self, req: CreateAgreementRequest) -> Agreement:
        now = self._now()
        agreement_id = f"agr-{uuid.uuid4().hex[:12]}"
        version = req.terms_version or _CURRENT_VERSIONS[req.product_type]

        agreement = Agreement(
            agreement_id=agreement_id,
            customer_id=req.customer_id,
            product_type=req.product_type,
            terms_version=version,
            status=AgreementStatus.SENT_FOR_SIGNATURE,
            signature_status=SignatureStatus.PENDING,
            created_at=now,
            updated_at=now,
            version_history=[version],
        )
        self._agreements[agreement_id] = agreement
        logger.info(
            "Agreement created: %s (customer=%s, product=%s, v=%s)",
            agreement_id,
            req.customer_id,
            req.product_type,
            version,
        )
        return agreement

    def get_agreement(self, agreement_id: str) -> Agreement:
        if agreement_id not in self._agreements:
            raise AgreementError(code="NOT_FOUND", message=f"Agreement {agreement_id} not found")
        return self._agreements[agreement_id]

    def record_signature(self, req: SignAgreementRequest) -> Agreement:
        agreement = self.get_agreement(req.agreement_id)
        if agreement.customer_id != req.customer_id:
            raise AgreementError(
                code="WRONG_CUSTOMER",
                message=f"Agreement {req.agreement_id} belongs to a different customer",
            )
        if agreement.signature_status == SignatureStatus.SIGNED:
            raise AgreementError(
                code="ALREADY_SIGNED",
                message=f"Agreement {req.agreement_id} is already signed",
            )
        if agreement.status in {AgreementStatus.TERMINATED, AgreementStatus.SUPERSEDED}:
            raise AgreementError(
                code="NOT_SIGNABLE",
                message=f"Agreement {req.agreement_id} status {agreement.status} cannot be signed",
            )

        now = self._now()
        agreement.signature_status = SignatureStatus.SIGNED
        agreement.status = AgreementStatus.ACTIVE
        agreement.signed_at = now
        agreement.updated_at = now
        agreement.signature_provider = req.signature_provider
        if req.docusign_envelope_id:
            agreement.docusign_envelope_id = req.docusign_envelope_id

        logger.info(
            "Agreement signed: %s (customer=%s, provider=%s, envelope=%s)",
            req.agreement_id,
            req.customer_id,
            req.signature_provider,
            req.docusign_envelope_id,
        )
        return agreement

    def supersede(self, agreement_id: str, new_version: str, operator_id: str) -> Agreement:
        """Replace this agreement with a new T&C version."""
        agreement = self.get_agreement(agreement_id)
        if agreement.status not in {AgreementStatus.ACTIVE, AgreementStatus.SENT_FOR_SIGNATURE}:
            raise AgreementError(
                code="CANNOT_SUPERSEDE",
                message="Only ACTIVE or SENT_FOR_SIGNATURE agreements can be superseded",
            )

        old_version = agreement.terms_version
        agreement.status = AgreementStatus.SUPERSEDED
        agreement.terms_version = new_version
        agreement.version_history.append(new_version)
        agreement.updated_at = self._now()
        agreement.signature_status = SignatureStatus.PENDING  # re-sign required

        logger.info(
            "Agreement superseded: %s v%s → v%s (by %s)",
            agreement_id,
            old_version,
            new_version,
            operator_id,
        )
        return agreement

    def list_customer_agreements(self, customer_id: str) -> list[Agreement]:
        return [a for a in self._agreements.values() if a.customer_id == customer_id]

    def get_current_terms_version(self, product_type: ProductType) -> TermsVersion:
        version = _CURRENT_VERSIONS[product_type]
        return TermsVersion(
            version=version,
            product_type=product_type,
            content_hash=_content_hash(product_type, version),
            effective_date=datetime(2026, 4, 1, tzinfo=UTC),
            is_current=True,
        )


# ── DocuSign stub ──────────────────────────────────────────────────────────────


class DocuSignStub:  # pragma: no cover
    """
    DocuSign integration stub — eIDAS Reg.910/2014 qualified e-signature.
    STATUS: STUB — requires DocuSign API key (CEO action).
    """

    def send_signature_request(self, agreement: Agreement, customer_email: str) -> str:
        raise NotImplementedError(
            "DocuSignStub: set DOCUSIGN_API_KEY + DOCUSIGN_ACCOUNT_ID, "
            "then implement REST POST to /envelopes."
        )


# ── Factory ────────────────────────────────────────────────────────────────────


def get_agreement_service() -> InMemoryAgreementService:
    return InMemoryAgreementService()
