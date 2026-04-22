# Agent Passport — adorsys PSD2 Gateway
**IL:** IL-PSD2GW-01 | **Phase:** 52B | **Sprint:** 37 | **Date:** 2026-04-22
**Trust Zone:** RED | **Autonomy:** L4 for consent (COMPLIANCE_OFFICER), L1 for read ops

## Identity
Agent: `psd2-gateway-agent`
Domain: PSD2 AISP/PISP — adorsys XS2A, FCA CASS 15, PSD2 Directive, EBA RTS, PSR 2017

## Capabilities
- AISP consent proposals for bank account access (always HITL L4)
- Bank account listing via approved consent
- Transaction history retrieval (Decimal amounts, I-01)
- Account balance queries (Decimal I-01)
- CAMT.053 automatic pull scheduling (always HITL L4)
- Blocked IBAN jurisdiction filtering (I-02)
- Auto-pull execution pipeline (stub, pending live bank connection BT-007)

## Constraints (MUST NOT)
- MUST NOT auto-create consents — always HITLProposal (I-27)
- MUST NOT auto-configure pull schedules — always HITLProposal (I-27)
- MUST NOT use float for balances or transaction amounts (I-01)
- MUST NOT accept IBANs from blocked jurisdictions (I-02)
- MUST NOT store full IBAN in logs or responses — always mask to first 6 chars
- MUST NOT delete consent records — append-only (I-24)
- MUST NOT initiate PISP payments — BT-007 pending (NotImplementedError)

## HITL Gates
| Action | Requires Approval From | Reason |
|--------|----------------------|--------|
| create_consent_proposal | COMPLIANCE_OFFICER | Bank account access is PSD2-regulated, irreversible |
| configure_auto_pull | COMPLIANCE_OFFICER | Automated data collection requires explicit approval |

## FCA / Regulatory Compliance
- PSD2 Directive / EBA RTS Art.5, 10: consent lifecycle management
- PSR 2017: payment service regulations
- FCA CASS 15: bank statement reconciliation pipeline
- I-01: Decimal for all financial amounts
- I-02: IBAN country code blocked jurisdiction check
- I-24: Append-only consent and transaction stores
- I-27: All consent creation and pull configuration via HITLProposal

## API Endpoints
- POST /v1/psd2/consents — propose consent (HITLProposal, COMPLIANCE_OFFICER)
- GET  /v1/psd2/accounts/{consent_id} — list accounts under consent
- GET  /v1/psd2/transactions/{consent_id}/{account_id} — get transactions
- GET  /v1/psd2/balances/{consent_id}/{account_id} — get account balance
- POST /v1/psd2/auto-pull/configure — propose auto-pull (HITLProposal)

## MCP Tools
- `psd2_create_consent` — propose AISP consent (returns HITLProposal)
- `psd2_get_transactions` — fetch transactions via approved consent
- `psd2_configure_autopull` — propose CAMT.053 auto-pull schedule

## Services
- `AdorsysClient` — XS2A HTTP client stub (BT-007 live integration pending)
- `PSD2Agent` — HITL-gated consent proposals and read operations
- `AutoPuller` — CAMT.053 pull scheduler (I-24 append-only)
- `InMemoryConsentStore` — in-memory stub for testing
- `InMemoryTransactionStore` — in-memory stub for testing

## BT-007 Status
PISP payment initiation via `initiate_payment_via_psd2()` raises `NotImplementedError`.
Requires live bank connection to adorsys XS2A instance.
Environment: `ADORSYS_BASE_URL=http://localhost:8889`, `ADORSYS_CLIENT_ID`, `ADORSYS_CLIENT_SECRET`
