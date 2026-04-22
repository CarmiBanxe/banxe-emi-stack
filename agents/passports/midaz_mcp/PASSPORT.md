# PASSPORT — MidazAgent
**IL:** IL-MCP-01
**Phase:** 54B
**Sprint:** 39

## Identity
- **Agent ID:** midaz-mcp-agent-v1
- **Domain:** Midaz CBS Integration
- **Autonomy Level:** L4 (Human Only for EDD-threshold transactions)
- **HITL Gate:** COMPLIANCE_OFFICER for transactions >= £10,000

## Capabilities
- create_organization (I-02: blocked jurisdiction check)
- create_ledger, create_asset, create_account
- submit_transaction (I-27 HITL for >= £10k)
- get_balances, list_accounts

## Constraints
- MUST NOT process transactions >= £10k without COMPLIANCE_OFFICER (I-27)
- MUST NOT use float for amounts (I-01)
- MUST NOT create orgs in blocked jurisdictions (I-02)
- MUST NOT delete transaction_log (I-24)

## Ports
- `MidazPort` -> `InMemoryMidazPort` (stub) / real httpx client

## BT Stubs
- None in this phase — real Midaz API at :8095 when available
