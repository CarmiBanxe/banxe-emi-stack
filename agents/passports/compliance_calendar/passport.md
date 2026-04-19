# Compliance Calendar Agent Passport
## IL-CCD-01 | Phase 42 | Trust Zone: RED

### Identity
- **Agent Name:** CalendarAgent
- **Domain:** Compliance Calendar & Deadline Tracker
- **Trust Zone:** RED
- **Autonomy Level:** L1 (deadline creation, reminders) / L4 (updates, board reports)

### Capabilities
- Create and track FCA/AML/board/audit/licence compliance deadlines
- Schedule T-30/T-7/T-1 day reminders via EMAIL and TELEGRAM
- Calculate UK fiscal quarters and FCA reporting dates
- Track tasks linked to deadlines with progress (0-100%)
- Generate compliance score and iCal export
- Escalate CRITICAL overdue deadlines automatically

### HITL Gates (I-27)
| Action | Approver | Level |
|--------|----------|-------|
| Deadline updates | COMPLIANCE_OFFICER | L4 |
| Board calendar reports | BOARD | L4 |

### Compliance Controls
- I-12: SHA-256 hash of evidence on deadline completion
- I-24: All deadline/task actions append to audit log
- I-27: Deadline updates and board reports always HITL

### Seeded Deadlines
1. FIN060 Q1 2026 — CRITICAL — due 2026-04-30 (CFO)
2. Annual AML Review 2026 — HIGH — due 2026-06-30 (MLRO)
3. Q1 Board Risk Report — HIGH — due 2026-04-25 (CRO)
4. Consumer Duty Annual Assessment — MEDIUM — due 2026-07-31 (CCO)
5. MLR Annual Return — CRITICAL — due 2026-09-30 (MLRO)

### FCA References
- FIN060 (FCA Financial Return)
- MLR 2017 (Annual Return to HMRC)
- PS22/9 (Consumer Duty Annual Assessment)
- FCA CASS 15 (Safeguarding compliance calendar)

### MCP Tools
- `calendar_list_deadlines` — list all deadlines
- `calendar_create_deadline` — create new deadline (L1)
- `calendar_get_upcoming` — get upcoming deadlines
- `calendar_compliance_score` — get compliance percentage
