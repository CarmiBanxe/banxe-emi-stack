# MCP Tools Rules — BANXE AI BANK
# Rule ID: 70-mcp-tools | Load order: 70
# Created: 2026-04-12 (IL-RETRO-02) | IL-MCP-01

## Location

All MCP tools live in **`banxe_mcp/server.py`** — single server, single file.
Import: `from banxe_mcp.server import mcp_server`.

## Tool Definition Pattern

```python
@mcp_server.tool()
async def verb_noun(param: str, optional: int = 10) -> str:
    """One-line docstring: what this tool does and why.

    Args:
        param: Description (required)
        optional: Description (default: 10)

    Returns:
        JSON string with results or error.
    """
    try:
        result = await _api_get(f"/v1/endpoint/{param}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
```

## Naming Convention

- **Format:** `verb_noun` (snake_case)
- **Verbs:** `get_`, `list_`, `run_`, `check_`, `query_`, `manage_`, `route_`, `monitor_`, `generate_`, `sync_`
- **Examples:** `get_account_balance`, `monitor_score_transaction`, `kb_query`
- Group related tools with consistent prefix: `kb_*`, `monitor_*`, `experiment_*`

## Mandatory Rules

1. **Every tool is async** — `async def`, never sync def.
2. **Always return a string** — JSON-serialised. Never return raw dicts or None.
3. **Wrap in try/except** — catch `httpx.HTTPStatusError` at minimum; return `{"error": "..."}` on failure.
4. **No direct DB access** — tools call internal FastAPI endpoints via `_api_get`/`_api_post`. Never import SQLAlchemy or ClickHouse clients directly.
5. **Audit trail** — any tool that mutates state (POST/PATCH) implicitly logs via the FastAPI endpoint. Do not add redundant logging in the tool itself.
6. **No secrets in tool responses** — never return raw API keys, tokens, or passwords.
7. **Decimal amounts as strings** — amounts in responses are strings (DecimalString), never `float`.

## Transport and Configuration

- Transport: **stdio** (MCP protocol).
- Server entry: `python -m banxe_mcp.server`.
- `.mcp.json` config: `{"banxe": {"command": "python", "args": ["-m", "banxe_mcp.server"]}}`.
- API base URL: `BANXE_API_BASE` env var (default: `http://localhost:8090`).

## Testing MCP Tools

```python
# Test pattern: patch _api_post/_api_get, not httpx directly
from unittest.mock import AsyncMock, patch

async def test_my_tool_returns_formatted_result():
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": "123", "status": "OK"}
        result = await my_tool("123")
        data = json.loads(result)
        assert data["id"] == "123"

async def test_my_tool_handles_http_error():
    with patch("banxe_mcp.server._api_get", side_effect=httpx.HTTPStatusError(...)):
        result = await my_tool("bad-id")
        assert "error" in json.loads(result)
```

## Adding a New Tool

Checklist before adding a new `@mcp_server.tool()`:
- [ ] Naming follows `verb_noun` pattern
- [ ] Docstring describes purpose, args, return
- [ ] `async def` + returns `str`
- [ ] Error handling: `try/except httpx.HTTPStatusError`
- [ ] Calls FastAPI endpoint (not DB directly)
- [ ] Test file in `tests/test_*/test_mcp_tools.py`
- [ ] Entry added to `docs/API.md` MCP Tools section

## References

- Server: `banxe_mcp/server.py`
- Tests: `tests/test_transaction_monitor/test_mcp_tools.py` (pattern reference)
- ADR: `docs/adr/ADR-004-fastmcp-agent-tooling.md`
- Current tool count: 34 tools
