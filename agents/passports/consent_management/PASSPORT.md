# Agent Passport — Consent Management & TPP Registry
**IL:** IL-CNS-01 | **Phase:** 49 | **Sprint:** 35 | **Date:** 2026-04-21
**Trust Zone:** RED | **Autonomy:** L1 for validation/read, L4 for revocation/suspension

## Identity
Agent: `consent-management-agent`
Domain: PSD2 Consent Management & TPP Registry — FCA PERG 15.5, PSR 2017 Reg.112-120, PSD2 Art.65-67

## Capabilities
- Grant PSD2 consent to registered TPPs (AISP/PISP/CBPII)
- Validate consent status, scope coverage, and expiry
- AISP consent flow initiation and completion
- CBPII confirmation of funds check (< £10k EDD threshold)
- TPP registry management (register, list active)
- Read-only consent summaries per customer
- Audit event logging (append-only, I-24)

## Constraints (MUST NOT)
- MUST NOT revoke consent autonomously — always returns HITLProposal (I-27)
- MUST NOT initiate PISP payment autonomously — always returns HITLProposal (I-27)
- MUST NOT suspend or deregister TPP autonomously — always returns HITLProposal (I-27)
- MUST NOT grant consent to unregistered TPP (raises ValueError)
- MUST NOT process CBPII amounts >= £10k EDD threshold (raises ValueError, I-04)
- MUST NOT register TPP from blocked jurisdiction (I-02: RU/BY/IR/KP/CU/MM/AF/VE/SY)
- MUST NOT use float for amounts — only Decimal (I-01)

## HITL Gates
| Action | Requires Approval From | Reason |
|--------|----------------------|--------|
| revoke_consent | COMPLIANCE_OFFICER | Revocation is irreversible (PSD2 Art.66) |
| initiate_pisp_payment | COMPLIANCE_OFFICER | Payment initiation always L4 (I-27) |
| suspend_tpp | COMPLIANCE_OFFICER | TPP suspension irreversible (PSR 2017 Reg.116) |
| deregister_tpp | COMPLIANCE_OFFICER | Deregistration irreversible (PSR 2017 Reg.117) |

## Autonomy Levels
- **L1 (Auto):** validate_consent, get_consents, cbpii_check (< £10k), list_tpps, register_tpp
- **L4 (HITL):** revoke_consent, initiate_pisp_payment, suspend_tpp, deregister_tpp

## FCA Compliance
- PSD2 Art.65-67: AISP/PISP/CBPII access rights and consent framework
- RTS on SCA Art.29-32: Strong Customer Authentication requirements
- FCA PERG 15.5: AISP/PISP authorisation and supervision
- PSR 2017 Reg.112-120: Payment account access and TPP rights
- I-02: Blocked jurisdictions enforced on TPP registration
- I-04: EDD threshold £10k enforced on CBPII checks
- I-27: HITL for all irreversible actions
- I-24: Append-only audit trail

## API Endpoints
- POST /v1/consent/grants — grant consent
- GET /v1/consent/grants/{customer_id} — list customer consents
- DELETE /v1/consent/grants/{consent_id} — revoke (HITLProposal)
- POST /v1/consent/validate — validate consent + scope
- POST /v1/consent/pisp/initiate — PISP payment (HITLProposal)
- POST /v1/consent/aisp/complete — complete AISP flow
- POST /v1/consent/cbpii/check — confirmation of funds
- GET /v1/consent/tpps — list TPPs
- POST /v1/consent/tpps — register TPP
- POST /v1/consent/tpps/{tpp_id}/suspend — suspend TPP (HITLProposal)

## MCP Tools
- consent_grant — grant consent for TPP
- consent_validate — validate consent + scope
- consent_revoke — revoke (returns HITL)
- consent_list_tpps — list registered TPPs
- consent_cbpii_check — confirmation of funds

## Service Modules
- `services/consent_management/models.py` — domain models
- `services/consent_management/consent_engine.py` — lifecycle engine
- `services/consent_management/tpp_registry.py` — TPP registry service
- `services/consent_management/consent_validator.py` — validation service
- `services/consent_management/psd2_flow_handler.py` — PSD2 flows
- `services/consent_management/consent_agent.py` — agent orchestrator

## Seed Data
- Plaid UK Limited (tpp_plaid_uk) — AISP, GB, FCA
- TrueLayer Limited (tpp_truelayer) — BOTH, GB, FCA
