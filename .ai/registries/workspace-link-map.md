# Workspace Link Map
# Source: CLAUDE.md §3, cross-repo references
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14)
# Migration Phase: 4
# Purpose: Map of all repos, their roles, and cross-references

## Repositories

| Repo | URL | Role | Status |
|------|-----|------|--------|
| **banxe-emi-stack** | github.com/CarmiBanxe/banxe-emi-stack | P0 Financial Analytics — FCA CASS 15 execution repo | ACTIVE |
| banxe-architecture | github.com/CarmiBanxe/banxe-architecture | Architecture, Instruction Ledger, ADR, COMPLIANCE-MATRIX | ACTIVE |
| vibe-coding | github.com/CarmiBanxe/vibe-coding | Compliance engine, AML stack, Midaz adapter (source of recon engine) | ACTIVE |

## Cross-references from banxe-emi-stack

| Source file | References | Target |
|-------------|------------|--------|
| CLAUDE.md §3 | Instruction Ledger | banxe-architecture/INSTRUCTION-LEDGER.md |
| CLAUDE.md §3 | Compliance Matrix | banxe-architecture/docs/COMPLIANCE-MATRIX.md |
| CLAUDE.md §3 | Financial Analytics Research | banxe-architecture/docs/financial-analytics-research.md |
| CLAUDE.md §4 | ReconciliationEngine origin | vibe-coding/src/compliance/recon/reconciliation_engine.py (commit 3f7060f) |
| CLAUDE.md §4 | StatementFetcher origin | vibe-coding/src/compliance/recon/statement_fetcher.py (commit 3f7060f) |
| CLAUDE.md §4 | Recon tests (T-16..T-30) | vibe-coding/src/compliance/recon/test_reconciliation.py |
| .claude/CLAUDE.md | Session continuity IL check | banxe-architecture/INSTRUCTION-LEDGER.md |

## Server infrastructure

| Host | Address | Role |
|------|---------|------|
| GMKtec | 192.168.0.72 | Production server — all services deployed |
| Legion | (local dev) | Development workstation, rsync source |

## Key external documentation

| Document | Location | Purpose |
|----------|----------|---------|
| Instruction Ledger | banxe-architecture/INSTRUCTION-LEDGER.md | Sequential task tracking (IL-001..IL-XXX) |
| COMPLIANCE-MATRIX | banxe-architecture/docs/COMPLIANCE-MATRIX.md | FCA requirement → implementation mapping |
| DOC-STANDARD | banxe-architecture/docs/DOC-STANDARD.md | Documentation canon (I-29) |
| PLANES | banxe-architecture/docs/PLANES.md | Developer / Product / Standby plane architecture |

---
*Last validated: 2026-04-10 (Phase 4 migration)*
