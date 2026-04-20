from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re

from services.kyb_onboarding.models import (
    ApplicationStore,
    BusinessApplication,
    BusinessType,
    DocumentType,
    HITLProposal,
    KYBDecision,
    KYBDecisionStore,
    KYBDocumentStore,
    KYBStatus,
    RiskTier,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}

REQUIRED_DOCS_BY_TYPE: dict[BusinessType, list[DocumentType]] = {
    BusinessType.LTD: [
        DocumentType.CERTIFICATE_OF_INCORPORATION,
        DocumentType.MEMORANDUM_ARTICLES,
    ],
    BusinessType.LLP: [
        DocumentType.CERTIFICATE_OF_INCORPORATION,
        DocumentType.SHAREHOLDER_REGISTER,
    ],
    BusinessType.SOLE_TRADER: [DocumentType.PROOF_OF_ADDRESS],
    BusinessType.PLC: [
        DocumentType.CERTIFICATE_OF_INCORPORATION,
        DocumentType.MEMORANDUM_ARTICLES,
        DocumentType.LATEST_ACCOUNTS,
    ],
    BusinessType.PARTNERSHIP: [
        DocumentType.PROOF_OF_ADDRESS,
        DocumentType.SHAREHOLDER_REGISTER,
    ],
    BusinessType.CHARITY: [DocumentType.CERTIFICATE_OF_INCORPORATION],
}


class ApplicationManager:
    def __init__(
        self,
        app_store: ApplicationStore,
        doc_store: KYBDocumentStore,
        decision_store: KYBDecisionStore,
    ) -> None:
        self._apps = app_store
        self._docs = doc_store
        self._decisions = decision_store

    def submit_application(
        self,
        business_name: str,
        business_type: BusinessType,
        companies_house_number: str,
        jurisdiction: str,
    ) -> BusinessApplication:
        if jurisdiction.upper() in BLOCKED_JURISDICTIONS:
            raise ValueError(f"I-02: jurisdiction {jurisdiction} is blocked")
        ts = datetime.now(UTC).isoformat()
        raw = f"{business_name}{ts}".encode()
        app_id = f"app_{hashlib.sha256(raw).hexdigest()[:8]}"
        app = BusinessApplication(
            application_id=app_id,
            business_name=business_name,
            business_type=business_type,
            companies_house_number=companies_house_number,
            jurisdiction=jurisdiction.upper(),
            status=KYBStatus.SUBMITTED,
            submitted_at=ts,
        )
        self._apps.save(app)
        self._audit(app_id, "submit_application", "system")
        return app

    def validate_documents(
        self,
        application_id: str,
        documents: list[dict],
    ) -> tuple[bool, list[str]]:
        app = self._apps.get(application_id)
        if app is None:
            return False, ["application_not_found"]
        if not self._valid_ch_number(app.companies_house_number, app.business_type):
            return False, ["invalid_companies_house_number"]
        required = REQUIRED_DOCS_BY_TYPE.get(app.business_type, [])
        provided = {d.get("document_type") for d in documents}
        missing = [r.value for r in required if r.value not in provided]
        return (len(missing) == 0, missing)

    def request_additional_docs(
        self,
        application_id: str,
        required_types: list[DocumentType],
        requestor: str,
    ) -> BusinessApplication:
        app = self._apps.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        updated = BusinessApplication(
            application_id=app.application_id,
            business_name=app.business_name,
            business_type=app.business_type,
            companies_house_number=app.companies_house_number,
            jurisdiction=app.jurisdiction,
            status=KYBStatus.DOCUMENTS_PENDING,
            submitted_at=app.submitted_at,
            ubo_ids=app.ubo_ids,
        )
        self._apps.save(updated)
        return updated

    def get_application(self, application_id: str) -> BusinessApplication | None:
        return self._apps.get(application_id)

    def list_applications(self, status: KYBStatus | None = None) -> list[BusinessApplication]:
        return self._apps.list_by_status(status)

    def update_status(
        self,
        application_id: str,
        new_status: KYBStatus,
        actor: str,
        reason: str,
    ) -> HITLProposal | BusinessApplication:
        app = self._apps.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        if new_status in (KYBStatus.APPROVED, KYBStatus.REJECTED):
            return HITLProposal(
                action=f"kyb_{new_status.value}",
                application_id=application_id,
                requires_approval_from="KYB_OFFICER",
                reason=reason,
            )
        updated = BusinessApplication(
            application_id=app.application_id,
            business_name=app.business_name,
            business_type=app.business_type,
            companies_house_number=app.companies_house_number,
            jurisdiction=app.jurisdiction,
            status=new_status,
            submitted_at=app.submitted_at,
            ubo_ids=app.ubo_ids,
        )
        self._apps.save(updated)
        return updated

    # --- helpers ---

    def _valid_ch_number(self, number: str, btype: BusinessType) -> bool:
        if btype in (BusinessType.SOLE_TRADER, BusinessType.PARTNERSHIP):
            return True  # no CH number required
        if btype == BusinessType.LLP:
            return bool(re.fullmatch(r"OC\d{6}", number))
        return bool(re.fullmatch(r"\d{8}", number))

    def _audit(self, application_id: str, action: str, actor: str) -> None:
        ts = datetime.now(UTC).isoformat()
        decision = KYBDecision(
            decision_id=f"audit_{hashlib.sha256(f'{application_id}{action}{ts}'.encode()).hexdigest()[:8]}",
            application_id=application_id,
            decision=KYBStatus.SUBMITTED,
            decided_by=actor,
            decided_at=ts,
            reason=action,
            risk_tier=RiskTier.LOW,
        )
        self._decisions.append(decision)  # I-24
