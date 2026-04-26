# PASSPORT — StatementAgent
**IL:** IL-CST-01 | **Phase:** 56C | **Sprint:** 41

## Identity
- Agent ID: client-statement-agent-v1
- Domain: Client Statement Service
- Autonomy Level: L4
- HITL Gate: OPERATIONS_OFFICER for manual corrections

## Capabilities
- generate() — PDF/CSV/JSON statements from Midaz ledger data
- Monthly auto-generation trigger
- BT-013: email_statement() → NotImplementedError (P1)

## Constraints
- MUST NOT auto-correct statements (I-27)
- MUST NOT use float for amounts (I-01)
- MUST NOT delete statement_log (I-24)
