# ADR-009: Blnk Finance for Safeguarding Position Tracking

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-043 + IL-013
**Author:** Moriel Carmi / Claude Code

---

## Context

FCA CASS 15 requires daily tracking of client money positions — the exact balance of segregated client funds held in each safeguarding account. The reconciliation workflow needs a position layer that:
1. Tracks client fund positions at account level (not just ledger transactions)
2. Integrates with the daily reconciliation cycle (Midaz → external bank statements)
3. Is self-hosted (data sovereignty)
4. Handles multi-currency positions

Midaz (primary CBS) records individual transactions but does not expose a position/snapshot API suitable for daily reconciliation. We need a complementary layer.

---

## Decision

**Blnk Finance** (open-source, self-hosted) alongside Midaz for client fund position tracking.

Daily reconciliation data flow:
```
Midaz ledger balance
        ↓
Blnk position snapshot
        ↓
bankstatementparser (CAMT.053 / MT940 → ExternalStatement)
        ↓
ReconciliationEngine (internal_balance ↔ external_balance)
        ↓
ReconResult (MATCHED / DISCREPANCY / PENDING)
        ↓
ClickHouse (safeguarding_events, 5yr TTL)
```

---

## Rationale

| Criterion | Blnk Finance | Custom position table | Mambu positions | SaaS reconciliation |
|-----------|-------------|----------------------|----------------|---------------------|
| Self-hosted | Yes | Yes | No (SaaS) | No (SaaS) |
| Multi-currency | Yes | Build required | Yes | Yes |
| Daily snapshot API | Yes | Build required | Yes | Yes |
| FCA data sovereignty | Yes | Yes | Depends on contract | No |
| OSS licence | Yes | N/A | No | No |
| Integration effort | Low (REST API) | Zero (own DB) | High (SaaS setup) | High (vendor) |

Blnk's position API provides exactly the "balance at date" queries needed for CASS 15 reconciliation without building a custom position service.

---

## Consequences

### Positive
- Separation of concerns: Midaz = double-entry ledger; Blnk = position/balance snapshots
- `InMemoryBlnkAdapter` stub enables reconciliation tests without Blnk running
- Blnk positions can be compared directly against CAMT.053 external statements

### Negative / Risks
- Two CBS-adjacent systems (Midaz + Blnk) to maintain
- Position drift possible if Blnk and Midaz are not kept in sync

### Mitigations
- Daily cron (`scripts/daily-recon.sh`) runs ReconciliationEngine which validates consistency
- Any Midaz/Blnk divergence surfaces as `DISCREPANCY` status — triggers BreachDetector

---

## References

- `services/recon/reconciliation_engine.py` — uses Blnk positions via LedgerPortProtocol
- `docker/docker-compose.recon.yml` — includes Blnk service
- `scripts/daily-recon.sh` — P0 CASS 7.15 cron (daily 07:00 UTC Mon-Fri)
- CLAUDE.md P0 Stack Map — Blnk Finance listed under RECONCILIATION
- IL-043: Safeguarding deployment on GMKtec (Blnk live)
