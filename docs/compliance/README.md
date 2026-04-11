# Compliance Documentation — BANXE AI Bank

This directory contains compliance control documentation for BANXE AI Bank EMI.

## Regulatory Framework

| Regulation | Scope | Status |
|------------|-------|--------|
| FCA CASS 15 | Safeguarding — daily reconciliation + FIN060 | P0 (deadline 7 May 2026) |
| MLR 2017 | AML/KYC, EDD, SAR filing | Implemented |
| PSR 2017 / APP 2024 | Payment services, PSD2 | Implemented |
| PS22/9 Consumer Duty | Customer outcomes, complaints | Implemented |
| EU AI Act Art.14 | Human oversight of AI decisions | Implemented (HITL gates) |
| POCA 2002 s.330 | SAR filing obligation | Implemented |

## Key Documents

- **Compliance Matrix**: [`banxe-architecture/docs/COMPLIANCE-MATRIX.md`](https://github.com/CarmiBanxe/banxe-architecture/blob/main/docs/COMPLIANCE-MATRIX.md)
- **Financial Invariants**: [`.claude/rules/financial-invariants.md`](../../.claude/rules/financial-invariants.md)
- **Agent Authority**: [`.claude/rules/agent-authority.md`](../../.claude/rules/agent-authority.md)
- **Domain Boundaries**: [`.claude/rules/compliance-boundaries.md`](../../.claude/rules/compliance-boundaries.md)

## Adding Compliance Docs

For each control:
1. State the regulatory reference (e.g., CASS 15.2.2R)
2. Describe the implementation (file path + function)
3. Describe the evidence trail (ClickHouse table, pgAudit)
4. State the human approval gate (MLRO / CFO / CEO)
