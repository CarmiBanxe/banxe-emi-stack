# Architecture: Banxe MCP Server

**IL:** IL-MCP-01 (IL-074) | **Created:** 2026-04-12
**ADR:** docs/adr/ADR-004-fastmcp-agent-tooling.md

---

## Overview

Central MCP (Model Context Protocol) server exposing all financial services as typed tools to Claude agents. Single entry point: `banxe_mcp/server.py`.

## Architecture

```
Claude Code / Claude API agent
        ↓ stdio (MCP protocol)
banxe_mcp/server.py
├── FastMCP instance (mcp_server)
├── _api_get(path) → httpx GET → FastAPI :8090
├── _api_post(path, data) → httpx POST → FastAPI :8090
└── _fx_get(path) → httpx GET → Frankfurter :8181
        ↓
FastAPI app (api/main.py, port :8090)
        ↓ Protocol DI
Services → PostgreSQL / ClickHouse / Redis / Midaz
```

## Tool Inventory (34 tools)

See `docs/API.md` → "MCP Tools Registry" for complete list.

### Tool Groups

| Group prefix | Count | IL | Service |
|-------------|-------|-----|---------|
| (financial) | 11 | IL-074 | ledger, payments, recon, kyc, aml, fx |
| (ARL) | 4 | IL-075 | agent routing layer |
| (design) | 4 | IL-077 | design system / Penpot |
| `kb_*` | 6 | IL-069 | compliance knowledge base |
| `monitor_*` | 5 | IL-071 | transaction monitor |
| `experiment_*` | 4 | IL-070 | experiment copilot |

## Transport

- **Protocol:** MCP (Anthropic Model Context Protocol)
- **Transport:** stdio
- **Entry point:** `python -m banxe_mcp.server`
- **Config:** `.mcp.json` → `{"banxe": {"command": "python", "args": ["-m", "banxe_mcp.server"]}}`

## Tool Pattern

Every tool:
1. Is `async def` + decorated `@mcp_server.tool()`
2. Calls FastAPI endpoint via `_api_get`/`_api_post` (never DB directly)
3. Returns `str` (JSON-serialised)
4. Handles `httpx.HTTPStatusError` → returns `{"error": "..."}`

## Testing Pattern

```python
# Patch at the _api_post/_api_get level — not httpx directly
with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
    mock.return_value = {"id": "123"}
    result = await my_tool("123")
    assert "123" in result
```

Reference: `tests/test_transaction_monitor/test_mcp_tools.py`

## Security

- Tools call FastAPI endpoints — auth is enforced at FastAPI level
- No direct DB access from MCP layer (security boundary)
- All mutating tools (POST/PATCH) log to ClickHouse via FastAPI service (I-24)
- No secrets returned in tool responses

## Adding New Tools

1. Add `@mcp_server.tool()` decorated function to `banxe_mcp/server.py`
2. Follow naming: `verb_noun` pattern (see `.claude/rules/70-mcp-tools.md`)
3. Add test to `tests/test_*/test_mcp_tools.py`
4. Update `docs/API.md` → MCP Tools Registry
5. Update `.ai/registries/agent-map.md`

## Files

```
banxe_mcp/
├── server.py    — 34 tools + FastMCP instance + _api_get/_api_post helpers
└── __init__.py
.mcp.json        — Claude Code MCP server config
tests/test_transaction_monitor/test_mcp_tools.py  — test pattern reference
```
