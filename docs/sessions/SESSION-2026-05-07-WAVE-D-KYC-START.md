# SESSION-2026-05-07-WAVE-D-KYC-START
# Wave D — KYC/Compliance Legacy Adapter Seam
# Branch: sprint5/wave-d-kyc-import-2026-05-07
# Canon: ADR-025 §15-16 + services/kyc/kyc_port.py + SESSION-2026-05-07-WAVE-C-PAYMENTS-START

---

## Context

Wave C (REWRITE-1..3) completed and merged (PR #82–84, SHA 726fc1b). Wave D begins
the KYC/Compliance import: classify legacy TypeScript KYC services from banxe-rar
and wire them behind `KYCWorkflowPort` (hexagonal seam, ADR-025 §15-16).

---

## Provider Stack (verified from evo1 staging)

| Provider | Source repo | Lines | Role |
|----------|------------|-------|------|
| **SumSub** (primary) | `banxe-fiat-backend/banxe-identity/src/sumsub-connector/` | 979+490 | Individual KYC/KYB via REST API |
| **BKYC** (B2B internal) | `banxe-fiat-backend/banxe-identity/src/bkyc/` | 668+120 | Legal entity KYB multi-step application |
| **Binance KYC** | `banxe-digital/binance-kyc/src/kyc/` | 621 | Crypto onboarding via Binance exchange API |
| **SumSub scoring** | `neuron/scoring-service/src/sumsub/` | ~300 | Risk scoring (separate domain, no REWRITE) |

Total KYC-relevant TS/PY files: **548** (filtered from 100,488-line rar listing)

---

## ADR-030 Status

**ADR-030_REQUIRED: NO**

`services/kyc/kyc_port.py` — `KYCWorkflowPort` **fully defined** with:
- 8-state enum: `PENDING → DOCUMENT_REVIEW → RISK_ASSESSMENT → EDD_REQUIRED → MLRO_REVIEW → APPROVED / REJECTED / EXPIRED`
- 3 customer types: `INDIVIDUAL`, `BUSINESS`, `SOLE_TRADER`
- 7 rejection reasons: `SANCTIONS_HIT`, `DOCUMENT_FRAUD`, `HIGH_RISK_JURISDICTION`, `PEP_NO_EDD`, `RISK_SCORE_TOO_HIGH`, `INCOMPLETE_DOCUMENTS`, `AML_PATTERN`
- Port methods: `create_workflow`, `get_workflow`, `submit_documents`, `approve_edd`, `reject_workflow`, `health`
- FCA MLR 2017 §18-27 compliance annotations, I-04 EDD threshold documented

---

## Transport Drop List (ADR-025 §15-16 — all to be dropped)

| Transport | TS class | Drop reason |
|-----------|----------|------------|
| TypeORM | `BKYCApplicationEntity`, `KYCInfoEntity`, `SumsubConfigEntity` | DB replaced by in-memory (Wave D) → PostgreSQL (Wave E) |
| RabbitMQ | `RabbitMQPublisherService`, `@RmqPattern` | Event bus dropped; pull-on-demand |
| gRPC | `GrpcCompaniesConnector`, `GrpcAddressesConnector`, `AbsLegalEntityConnector` | gRPC transport dropped |
| NestJS DI | `@Injectable`, `@InjectRepository`, `@TryCatch` | DI framework dropped |
| SumSub HMAC client | `SumsubClient` (axios) | HTTP client dropped; domain logic mapped |
| GraphQL resolvers | `@Resolver`, `@Query`, `@Mutation` | API layer dropped |
| Amplitude | `AmplitudeService` | Analytics dropped |
| ConfigService | `ConfigService.get('SUMSUB_SOURCE_KEY')` | Config dropped |

---

## Top-3 REWRITE Candidates

### REWRITE-4 — LegacySumSubAdapter (PRIMARY)
**Source**: `sumsub-connector.service.ts` (979 lines) + `sumsub-connector-applicant.service.ts` (490 lines)
**Port**: `KYCWorkflowPort` (`services/kyc/kyc_port.py`)
**Target**: `services/compliance/legacy/legacy_sumsub_adapter.py`

| TS method | Python mapping |
|-----------|----------------|
| `createApplicant(dto)` | `create_workflow(request)` → `KYCStatus.PENDING` |
| `submitUserDocuments(payload)` | `submit_documents(workflow_id, document_ids)` → `DOCUMENT_REVIEW` |
| `applicantReviewed(payload)` | `_handle_webhook(payload)` → internal state advance |
| `approveApplicant(id)` | `approve_edd(workflow_id, mlro_user_id)` → `APPROVED` |
| `declineApplicant(id, reason)` | `reject_workflow(workflow_id, reason)` → `REJECTED` |
| `getApplicantData(id)` | `get_workflow(workflow_id)` |
| `getAccessToken(dto)` | (out of port scope — separate accessor) |
| `checkCryptoTransaction(dto)` | DROP (scoring domain) |

Transport DROP: SumsubClient HMAC, TypeORM repositories, gRPC connectors, NestJS DI.

### REWRITE-5 — LegacyBKYCAdapter (B2B)
**Source**: `bkyc.service.ts` (668 lines) + `bkyc-document.service.ts`
**Port**: `KYCWorkflowPort` (kyc_type=BUSINESS)
**Target**: `services/compliance/legacy/legacy_bkyc_adapter.py`

| TS method | Python mapping |
|-----------|----------------|
| `createBlankApplication(dto)` | `create_workflow(KYCType.BUSINESS)` → `PENDING` |
| `fillUpApplication(dto)` | in-memory update to workflow fields |
| `updateApplicationStep(dto)` | internal checkpoint (no port method) |
| `acceptApplication(dto)` | `approve_edd(workflow_id, mlro_user_id)` → `APPROVED` |
| `declineApplication(dto)` | `reject_workflow(workflow_id, reason)` → `REJECTED` |
| `searchApplications(dto)` | (list method, beyond port) |
| ABS scoring integration | DROP (AbsScoringConnector) |
| RabbitMQ publish | DROP |

### REWRITE-6 — LegacyBinanceKYCAdapter
**Source**: `binance-kyc/kyc.service.ts` (621 lines)
**Port**: `KYCWorkflowPort` (limited — KYC URL flow, webhook-only status)
**Target**: `services/compliance/legacy/legacy_binance_kyc_adapter.py`

| TS method | Python mapping |
|-----------|----------------|
| `generateKYCURL(dto)` | `create_workflow()` → returns PENDING with URL in notes |
| `handleKYCWebhook(dto)` | state advance → APPROVED / REJECTED |
| `checkKYCStatus(dto)` | `get_workflow(workflow_id)` |
| `createSubAccount(dto)` | DROP (Binance exchange API) |
| `linkMultipleAccounts(dto)` | DROP (account linking) |
| RabbitMQ publish | DROP |

---

## Adapter Seam Plan

```
services/compliance/
└── legacy/
    ├── __init__.py                      # stub: "KYC/AML legacy adapters behind KYCWorkflowPort (Wave D)"
    ├── legacy_sumsub_adapter.py         # REWRITE-4 (PRIMARY) — Wave D Step 2
    ├── legacy_bkyc_adapter.py           # REWRITE-5 — Wave D Step 3
    └── legacy_binance_kyc_adapter.py   # REWRITE-6 — Wave D Step 4
```

Existing port (unchanged):
```
services/kyc/
├── kyc_port.py          # KYCWorkflowPort — fully defined, ADR-030 NOT required
└── mock_kyc_workflow.py # MockKYCWorkflow — test stub (in use)
```

---

## Frozen Files (Wave D — DO NOT TOUCH)

- `api/routers/auth.py`
- `services/auth/**`
- `services/payment/**` (Wave C frozen)
- `services/kyc/kyc_port.py` (port is complete, no changes)
- `services/kyc/mock_kyc_workflow.py` (test stub, no changes)
- `decisions/ADR-{001..029}*.md`

---

## Invariants

- I-01: `Decimal` for all monetary thresholds (EDD £10k / £50k)
- I-02: Block RU/BY/IR/KP/CU/MM/AF/VE/SY — must propagate to `RejectionReason.HIGH_RISK_JURISDICTION`
- I-24: `KYCAuditRecord` (append-only) separate from `KYCWorkflowResult` — Wave D→ClickHouse sink
- I-27: MLRO gate on EDD_REQUIRED → APPROVED (L4 Human Only) — `approve_edd()` must record mlro_user_id

---

## Quality Gate

- `ruff check .` — 0 issues
- `ruff format` — clean
- `pytest tests/ -x -q --no-cov` — all green
- `semgrep --config .semgrep/banxe-rules.yml --error` — 0 findings
- ≥ 15 tests per adapter (ADR-025 rule 30-testing.md)
- Coverage ≥ 80%
