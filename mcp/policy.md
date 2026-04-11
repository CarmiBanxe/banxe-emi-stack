# MCP Policy — BANXE AI Bank
# IL-SK-01 | Created: 2026-04-11

## Core Principle: Read-Only First

All MCP server interactions default to **read-only mode**.
A tool that reads data requires no special approval.
A tool that writes, modifies, or triggers side effects requires explicit justification and,
for production systems, human approval.

## Allowed MCP Operations (no approval needed)

| Category | Examples |
|----------|---------|
| **Docs lookup** | Fetch API docs, runbooks, architectural specs |
| **Ticket lookup** | Read GitHub issues, IL entries, ADRs |
| **Schema introspection** | Read DB schema, dbt model definitions |
| **Operational metadata** | Health checks, tool inventory, service status |
| **Read-only queries** | SELECT queries on non-sensitive tables |

## Restricted MCP Operations (require explicit approval)

| Category | Approval required from |
|----------|----------------------|
| **Write to production** | CTIO + engineer pair review |
| **Secret access** | CTIO + MLRO (if compliance-sensitive) |
| **Irreversible operations** | Human approval before execution (QRAA protocol) |
| **Schema changes** | CTIO + DBA review |
| **Mass data operations** | MLRO + CFO if financial data affected |

## MCP Server Registration Requirements

Every MCP server integrated with BANXE must be documented with:

| Field | Description |
|-------|-------------|
| **Owner** | Team or person responsible for the server |
| **Scope** | What data/systems the server can access |
| **Classification** | public / internal / confidential / restricted |
| **Approval** | Who approved the integration and when |
| **Tools** | List of all registered tools with docstrings |
| **Registry entry** | Entry in `.ai/registries/agent-map.md` |

## Current MCP Servers

| Server | Owner | Scope | Port |
|--------|-------|-------|------|
| banxe-mcp | Platform team | Recon, ledger, reporting, health | 9100 |

## Tool Requirements

Every registered MCP tool MUST have:
- A docstring (Semgrep rule `banxe-mcp-tool-must-have-docstring`)
- Full type annotations on all parameters and return type
- No bare `raise Exception(...)` (Semgrep rule `banxe-mcp-no-raw-exception`)
- Entry in `.ai/registries/agent-map.md` tool inventory

## References

- MCP server: `banxe_mcp/server.py`
- Health workflow: `agents/compliance/workflows/mcp_health_workflow.py`
- Agent registry: `.ai/registries/agent-map.md`
- Slash command: `.claude/commands/mcp-status.md`
