# ArchiMate Map — banxe-emi-stack / banxe-architecture
# Source: banxe-architecture/scripts/import_archimate.py, .ai/registries/
# Created: 2026-04-13 (Sprint 13: S13-00 ArchiMate import pipeline) | Updated: 2026-04-13 (Sprint 14)
# Migration Phase: 13
# Purpose: ArchiMate 3.2 model elements, relations, views — AI-readable registry

## Overview

| Attribute | Value |
|-----------|-------|
| Standard | ArchiMate 3.2 (Open Group) |
| Import script | `banxe-architecture/scripts/import_archimate.py` |
| Input formats | Archi Open Exchange XML, CSV export |
| Output format | JSON (`banxe-architecture/exchange/*.json`) |
| Makefile target | `make import` (banxe-architecture) |
| Tests | `tests/test_import_archimate.py` — 32 tests |
| Commit | `feat(S13-00): ArchiMate import pipeline` |

## Element types supported

| ArchiMate type | Layer | Banxe usage |
|----------------|-------|-------------|
| ApplicationComponent | Application | Microservices (payment, kyc, iam...) |
| ApplicationService | Application | Service interfaces |
| BusinessProcess | Business | Onboarding, reconciliation, reporting |
| BusinessRole | Business | Operator, MLRO, Customer |
| BusinessActor | Business | FCA, Banxe, Partner banks |
| TechnologyService | Technology | CBS (Midaz), ClickHouse, Redis |
| TechnologyNode | Technology | EC2 nodes, K8s pods |
| DataObject | Application | Schemas, ledger entries |
| Constraint | Motivation | Regulatory constraints (FCA, PSD2) |
| Requirement | Motivation | Product requirements |
| Goal | Motivation | Strategic objectives |
| Principle | Motivation | Architecture principles |
| AssessmentElement | Motivation | Risk assessments |

## Relationship types supported

| ArchiMate relation | Meaning | Example |
|--------------------|---------|---------|
| Serving | A serves B | PaymentService serves LedgerService |
| Composition | A is composed of B | EMIStack is composed of kyc, aml |
| Triggering | A triggers B | PaymentSubmitted triggers AMLCheck |
| Association | General | PaymentService — FCA_Requirement |
| Realization | A realises B | AuthAdapter realises IAMPort |
| Aggregation | A aggregates B | BankingCore aggregates ledger, payment |

## Property definitions (banxe-specific)

| Property key | Values | Used for |
|-------------|--------|---------|
| banxe-domain | payment, kyc, aml, iam, ... | Domain boundary tagging |
| banxe-status | ACTIVE, STUB, PLANNED | Implementation status |
| banxe-host | internal, external | Hosting location |
| banxe-il | IL-NNN | Instruction-Ledger reference |
| banxe-phase | 1-13 | Sprint/phase number |

## JSON output schema (per element)

```json
{
  "id": "elem-1",
  "name": "Payment Service",
  "type": "ApplicationComponent",
  "documentation": "Handles FPS and SEPA payments.",
  "banxe_domain": "payment",
  "properties": {
    "banxe-domain": "payment",
    "banxe-status": "ACTIVE"
  }
}
```

## JSON output schema (per relationship)

```json
{
  "id": "rel-1",
  "type": "Serving",
  "source": "elem-1",
  "target": "elem-3",
  "name": ""
}
```

## Known models (banxe-architecture/exchange/)

| File | Source | Description |
|------|--------|-------------|
| `banxe-emi-main.json` | Archi XML export | Full EMI stack architecture |
| `banxe-payments.json` | CSV export | Payment service elements |
| `banxe-compliance.json` | CSV export | AML/KYC/fraud service elements |

## AI agent usage

The archimate-map feeds the following agents:
- **ArchitectureSkillOrchestrator** — reads element/relation graphs to answer design questions
- **ComplianceAgent** — maps regulatory requirements to ArchiMate Motivation elements
- **ReportingAgent** — uses BusinessProcess elements for FIN060 process context

## File locations

| Path | Purpose |
|------|---------|
| `banxe-architecture/scripts/import_archimate.py` | Import pipeline (renamed from import-archimate.py) |
| `banxe-architecture/Makefile` | `make import` target |
| `banxe-architecture/exchange/` | JSON output directory |
| `banxe-emi-stack/tests/test_import_archimate.py` | 32 unit tests |
| `banxe-business-processes/exchange/` | Business process ArchiMate exports |
