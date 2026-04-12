# ADR-004: FastMCP as AI Agent Tool Protocol

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-MCP-01 (IL-074)
**Author:** Moriel Carmi / Claude Code

---

## Context

AI agents (ARL, Compliance KB, Experiment Copilot, Transaction Monitor) need to call financial services safely. The interface must:

1. Be typed and introspectable (agents know what tools exist and their signatures)
2. Provide an audit trail for all calls (regulatory requirement)
3. Isolate agents from direct DB access (security boundary)
4. Be compatible with Claude Code / Claude API agent loops

Options evaluated:
- **Direct function imports**: tight coupling, no isolation, no audit
- **REST API calls**: works, but agents need HTTP client + error handling boilerplate
- **gRPC**: typed, but adds protobuf build step + Go/Java-centric tooling
- **MCP (Model Context Protocol)**: Anthropic's standard for Claude agent tools; stdio transport; introspectable; emerging standard

---

## Decision

**FastMCP** (`fastmcp` Python library) implementing Anthropic's Model Context Protocol via stdio transport.

All 34 tools are defined in `banxe_mcp/server.py`. Each tool:
1. Is a typed `async def` function decorated with `@mcp_server.tool()`
2. Calls the internal FastAPI endpoint (never the DB directly)
3. Returns a JSON string
4. Handles errors via `try/except httpx.HTTPStatusError`

---

## Rationale

| Criterion | FastMCP / MCP | Direct function call | REST (httpx) | gRPC |
|-----------|-------------|---------------------|--------------|------|
| Claude agent compatibility | Native | Requires tool wrapper | Custom wrapper | Custom wrapper |
| Tool introspection | Built-in (schema) | No | OpenAPI | protobuf |
| Audit trail | Per-tool (via FastAPI layer) | Manual | Manual | Manual |
| DB isolation | Enforced (calls FastAPI) | Must enforce manually | Enforced | Enforced |
| Typed parameters | Yes (Python type hints → JSON schema) | Yes | OpenAPI schema | Yes |
| Emerging standard | Yes (Anthropic MCP) | No | No | No |

---

## Architecture

```
Claude agent / MCP client
        ↓ stdio (MCP protocol)
banxe_mcp/server.py  ← @mcp_server.tool() definitions
        ↓ httpx (_api_get / _api_post)
FastAPI app (port :8090)
        ↓ dependency injection
Services / Ports (LedgerPort, AlertStore, etc.)
        ↓
PostgreSQL / ClickHouse / Redis
```

The MCP layer is a **thin adapter** — no business logic. All logic is in FastAPI services.

---

## Consequences

### Positive
- 34 tools available to all Claude agents in the workspace
- Single entry point for all agent→service calls — easy to add audit middleware
- `_api_post`/`_api_get` helpers are mockable in tests (`patch("banxe_mcp.server._api_post")`)
- `.mcp.json` wires the server automatically in Claude Code

### Negative / Risks
- MCP is relatively new — FastMCP API may change
- All tools in one file (server.py) — risk of god-file as tool count grows
- stdio transport requires the MCP server process to be running

### Mitigations
- FastMCP version pinned in `requirements.txt`
- Tool grouping by prefix (`kb_*`, `monitor_*`, `experiment_*`) keeps server.py navigable
- `_api_get`/`_api_post` failure returns `{"error": "..."}` — agents gracefully handle unavailability

---

## References

- `banxe_mcp/server.py` — 34 tools
- `.mcp.json` — server configuration
- `.claude/rules/70-mcp-tools.md` — development rules
- `tests/test_transaction_monitor/test_mcp_tools.py` — test pattern reference
- ADR-005: Protocol DI (the pattern used in FastAPI layer below MCP)
