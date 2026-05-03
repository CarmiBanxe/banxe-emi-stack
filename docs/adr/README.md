# Architecture Decision Records — BANXE AI Bank

This directory contains Architecture Decision Records (ADRs) for BANXE AI Bank.

## Format

Each ADR is a separate file named `ADR-NNN-short-title.md`.

### ADR Template

```markdown
# ADR-NNN: Short Title

**Date**: YYYY-MM-DD
**Status**: proposed / accepted / deprecated / superseded

## Context
What situation or problem led to this decision?

## Decision
What decision was made?

## Consequences
What are the positive and negative consequences of this decision?

## Alternatives Considered
What other options were evaluated and why were they rejected?
```

## Existing Decisions

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](ADR-001-biome-vs-eslint.md) | Biome vs ESLint/Prettier | Accepted | — |
| [ADR-002](ADR-002-clickhouse-audit-log.md) | ClickHouse for Audit Log | Accepted | — |
| [ADR-003](ADR-003-midaz-core-banking.md) | Midaz as Core Banking System | Accepted | — |
| [ADR-004](ADR-004-fastmcp-agent-tooling.md) | FastMCP for Agent Tooling | Accepted | — |
| [ADR-005](ADR-005-protocol-di-pattern.md) | Protocol DI Pattern | Accepted | — |
| [ADR-006](ADR-006-weasyprint-fin060.md) | WeasyPrint for FIN060 PDF | Accepted | — |
| [ADR-007](ADR-007-decimal-for-money.md) | Decimal for Money (I-01) | Accepted | — |
| [ADR-008](ADR-008-fastapi-web-framework.md) | FastAPI as Web Framework | Accepted | — |
| [ADR-009](ADR-009-blnk-position-tracking.md) | Blnk for Position Tracking | Accepted | — |
| [ADR-013](ADR-013-swift-correspondent.md) | SWIFT Correspondent Banking | Accepted | — |
| [ADR-014](ADR-014-fx-engine.md) | FX Engine (Frankfurter ECB) | Accepted | — |
| [ADR-015](ADR-015-auth-ports.md) | Auth Ports (Keycloak) | Accepted | — |
| [ADR-021](ADR-021-ai-plane-pii-aml-routing.md) | AI Plane and PII/AML Routing | Accepted | 2026-05-03 |

## When to Create an ADR

Create an ADR when:
- Introducing a new external dependency
- Changing domain ownership or service boundaries
- Making a compliance-significant architectural choice
- Choosing between two substantially different approaches

Reference: [`.claude/commands/architecture-review.md`](../../.claude/commands/architecture-review.md)
