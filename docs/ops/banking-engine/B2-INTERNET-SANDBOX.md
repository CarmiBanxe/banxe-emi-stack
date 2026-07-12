# B-2 — Internet Access (Controlled, PSD2 Sandbox)

| Field        | Value                                              |
|--------------|----------------------------------------------------|
| Sprint       | B-2                                                |
| Branch       | agent/factory/bankingengine/b2-psd2-sandbox        |
| Status       | IN PROGRESS                                        |
| Scope        | SANDBOX ONLY — no live PSD2/XS2A, no real creds    |

---

## Scope

Banking Engine B-2 introduces *controlled* outbound access limited to:

1. **Adorsys PSD2 / XS2A stub** — returns a synthetic CAMT.053 bank statement
   (fake IBAN `TEST00000000000000`; no real bank connection).
2. **MCP ledger + CRM stub** — returns synthetic ledger/customer test data
   (no real Midaz or CRM endpoint).
3. **Egress logger** — every outbound call carries `X-Request-ID` and is
   appended to the sandbox egress log (`logs/banking-engine-egress.jsonl`).

All outbound traffic in the banking zone is **blocked at network level**
(no external internet routes).  Data flows only via the logged API gateway.
This is verified by the operator at infrastructure level, not by code.

---

## Done Criteria

| # | Criterion | Verified by |
|---|-----------|-------------|
| 1 | `AdorsysPsd2Stub.get_camt053_statement()` returns a dict with `document_type == "CAMT.053"` | `test_b2_stubs.py` |
| 2 | All entries in the statement carry `is_test_data: true` | `test_b2_stubs.py` |
| 3 | `McpLedgerStub.get_balance()` returns synthetic GBP balance with `is_test_data: true` | `test_b2_stubs.py` |
| 4 | `EgressSession.prepare_headers()` returns `X-Request-ID` header; `log_egress` appends to log | `test_b2_stubs.py` |
| 5 | Banking zone has NO external internet routes | Operator verification (infra) |
| 6 | Ruff lint + format: zero issues | CI / local `ruff check && ruff format` |

---

## Network Isolation (Correction 4)

The banking zone executes on a network segment with **no external internet routes**.
All allowed outbound traffic is routed exclusively through the logged API gateway,
which enforces:

- `X-Request-ID` header on every request (applied by `EgressSession`)
- Append-only egress log at `logs/banking-engine-egress.jsonl`
- URL sanitisation before logging (query params stripped; no PII in log)

**This network boundary is enforced at infrastructure level by the operator —
it is not enforced by application code.**

---

## GAPs (Out of Scope for B-2)

| GAP ID | Description |
|--------|-------------|
| OI-2   | Production firewall rules for banking zone — operator task, not code |
| OI-3   | Real Adorsys PSD2 credentials — out of scope until B-3 production path |
| OI-4   | Live CAMT.053 parsing from real bank feed — out of scope for sandbox |

---

## Artifacts

| Path | Purpose |
|------|---------|
| `services/banking-engine/stubs/adorsys_psd2_stub.py` | PSD2/XS2A CAMT.053 mock |
| `services/banking-engine/stubs/mcp_ledger_stub.py`   | MCP ledger + CRM mock |
| `services/banking-engine/egress_logger.py`            | Egress X-Request-ID logger |
| `services/banking-engine/tests/test_b2_stubs.py`     | Sandbox unit tests (no network) |
| `ledger/entries/banking-engine-b1-close/`            | B-1 close ledger event |

---

## References

- B-0 sandbox declaration: `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`
- B-1 LangGraph runbook: `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md`
- Compliance gates: `docs/ops/banking-engine/COMPLIANCE-GATES.md`
- API Contract egress rule: CLAUDE.md §API Contracts + `egress_logger.py`
