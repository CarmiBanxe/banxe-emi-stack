# ADR-003: Midaz as Primary Core Banking System (CBS)

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-009
**Author:** Moriel Carmi / Claude Code
**Note:** Mirrors banxe-architecture/ADR-013

---

## Context

An EMI requires a double-entry ledger as the authoritative source of truth for all client fund balances. Options evaluated:

1. **SaaS CBS** (Mambu, Thought Machine, Modulr ledger): managed, but expensive, vendor lock-in, and data sovereignty concerns under FCA data localisation expectations.
2. **Build custom**: full control, but 12+ months dev time — not viable for 7 May 2026 P0 deadline.
3. **OSS self-hosted CBS**: open-source, self-hosted, no recurring SaaS fees.

---

## Decision

**Midaz** (open-source CBS by LedgerFi, self-hosted, port `:8095`) as the primary Core Banking System.

Architecture: **LedgerPort ABC** pattern — `LedgerPortProtocol` (Python Protocol) abstracts Midaz behind a clean interface. Consumers never import Midaz client directly.

---

## Rationale

| Criterion | Midaz (self-hosted) | Mambu/Thought Machine (SaaS) | Custom build |
|-----------|--------------------|-----------------------------|-------------|
| Cost | Free (OSS) | £50k+/yr | Dev cost only |
| Data residency | Full control (GMKtec, UK) | Vendor datacenter | Full control |
| Vendor lock-in | None | High | None |
| FCA data sovereignty | Yes | Depends on contract | Yes |
| Time to deploy | < 1 day (Docker) | Months (contract + integration) | 12+ months |
| Double-entry ledger | Yes (native) | Yes | Must build |
| REST API | Yes (:8095) | Yes | Must build |
| Multi-currency | Yes | Yes | Must build |

---

## Consequences

### Positive
- Full data sovereignty: all client fund data stays on Banxe-controlled infrastructure
- `LedgerPortProtocol` + `StubLedgerAdapter` enables full test suite without Midaz running
- No recurring SaaS costs for a licensed EMI

### Negative / Risks
- Midaz is a relatively young OSS project — breaking changes in minor versions
- Self-hosting means Banxe owns ops burden (HA, backup, upgrade)
- Midaz `create_transaction` API is `NotImplementedError` in the current stub — CEO action needed to wire up live transaction posting

### Mitigations
- `StubLedgerAdapter` and `InMemoryLedgerAdapter` provide full test coverage regardless of Midaz status
- Midaz version pinned in `docker/docker-compose.*.yml`
- Deviation documented in IL-009: `create_transaction → NotImplementedError (Transaction API pending)`

---

## Key API Calls

```python
from services.ledger.midaz_client import MidazClient

client = MidazClient()
balance = await client.get_balance(org_id, ledger_id, account_id)  # → Decimal
# create_transaction: pending CEO action (IL-009 deviation)
```

---

## References

- `services/ledger/midaz_client.py` — MidazClient + LedgerPortProtocol
- `services/ledger/midaz_adapter.py` — MidazLedgerAdapter + StubLedgerAdapter
- banxe-architecture/ADR-013 — canonical reference
- IL-009: P0 skeleton + Midaz integration
