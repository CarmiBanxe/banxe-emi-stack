# Factory Org-Structure — EMI BANXE AI Bank (full-cycle IT company)

Source concept: operator's company-design doc (Team Topologies + Spotify model +
Inverse Conway). Canon: docs/canon/operating-mode.md (Central=read-only brain/orders,
Factory=full-cycle execution: build → save → analyse → document).

This file is the ORG INDEX. It does NOT restate job descriptions — each employee's
job description IS its passport/soul file (agents/passports/*, agents/compliance/soul/*).
HITL authority backbone is code: services/hitl/org_roles.py (OrgRole + HITLGate, SMF-mapped).

## C-Suite (SMF-mapped, from services/hitl/org_roles.py)
| Role | SMF | Authority |
|------|-----|-----------|
| CEO | SMF1 | ultimate accountability; co-signs AI model update, sanctions reversal |
| CFO | SMF2 | financial sign-off (FIN060, restatements) |
| CRO | SMF4 | risk; AI model update approval |
| INTERNAL_AUDITOR | SMF5 | audit independence |
| MLRO | SMF17 | SAR, PEP, sanctions, EDD decisions (non-delegable) |
| COO | SMF24 | operations |
| CTO | SMF26 | technology, Jube adapter |
| COMPLIANCE_OFFICER | (certified) | AML/TM/CDD human-double; owns pre-compliance research |
| OPERATOR | — | operations staff within limits |

## Team Topologies — Squads (stream-aligned) → employees (passports/souls)
Each squad = a BANXE domain; members = agent passports (their job descriptions).

- **Payments Core** → passports: batch_payments, scheduled_payments, psd2_gateway, beneficiary, fee_management
- **KYC / Identity** → passports: kyb_onboarding, customer_lifecycle, consent_management, device_fingerprint
- **Crypto & Blockchain** → passports: crypto, midaz_mcp
- **Trading / FX** → passports: fx, fx_engine, fx_rates, multicurrency
- **Customer AI Agent / CRM** → passports: notifications, preferences, complaints, disputes, loyalty, referral, support
- **Compliance & Reporting** → compliance souls: mlro_agent, aml_check_agent, tm_agent, sanctions_check_agent,
  cdd_review_agent, fraud_detection_agent, jube_adapter_agent, recon_analysis_agent, risk_management,
  breach_prediction_agent + passports: fatca_crs, compliance_auto, compliance_calendar, compliance_sync,
  consumer_duty, reporting_analytics, sanctions_screening, fraud_tracer
- **Cards & Accounts** → passports: cards, lending, savings, insurance, merchant
- **Platform / Infra** → passports: gateway, api_versioning, observability, multi_tenancy, open_banking,
  swift_correspondent, audit, audit_trail, reconciliation, client_statements, documents

## Enabling / Complicated-Subsystem (per operator doc)
- **Quality Factory (Chapter QA)** → .githooks/role-guard.sh + quality scan (semgrep banxe-rules),
  scripts/quality-gate.sh, CI .github/workflows/quality-gate.yml (coverage gate).
- **Architecture Enablement (Guild of Architecture)** → docs/adr/* (ADR canon), Architecture Review Board.
- **AI Enablement (LLMOps/AgentOps)** → Grok-lane (ADR-043), fable-advisor, adverse_media multi-node feeds.
- **Core Ledger & Settlement (Complicated Subsystem)** → services/ledger/*, src/settlement/*, src/safeguarding/*.

## Chain of command (canon)
- **Central terminal** = brain/orders (read-only; issues specs). Does NOT mutate repos.
- **Factory terminal (this one, .TERMINAL-ROLE=FACTORY)** = full-cycle IT company: writes, saves,
  analyses (quality gates), documents (ADR/docs). Mutations happen here (operating-mode.md §3).
- Product/regulatory DECISIONS stay with the SMF-holders above (MLRO/CEO/etc.) via HITL gates.

## How an employee's job description is bound
- Product-domain agent → agents/passports/<name>/PASSPORT.md (or SOUL.md + *_agent.yaml)
- Compliance agent → agents/compliance/soul/<name>.soul.md
- HITL authority a role can exercise → services/hitl/org_roles.py (OrgRole, HITLGate)
- Decision method / trust zone / autonomy → each passport's Decision Method section (ADR-030)

Counts: 51 passports + 18 compliance souls. This index is append-only; add new employees by
adding their passport/soul and a squad line here.
