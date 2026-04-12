# Runbook: MCP Server

**Module:** `banxe_mcp/server.py`
**Transport:** stdio (MCP protocol)
**Config:** `.mcp.json`
**Total tools:** 34

---

## 1. Start / Stop

The MCP server is launched automatically by Claude Code via `.mcp.json`. For manual testing:

```bash
# Start manually
python -m banxe_mcp.server

# Test tool availability (Claude Code)
# In Claude Code prompt: run mcp tool get_account_balance {"account_id": "test"}
```

---

## 2. Check Tool Availability

```bash
# List all available tools (from Claude Code)
# Claude Code auto-discovers tools from .mcp.json
# Verify by running any tool and checking for response
```

---

## 3. Debug Tool Call Failures

1. Check FastAPI is running: `curl http://localhost:8090/health`
2. Check Frankfurter is running (for FX tools): `curl http://localhost:8181/v1/latest?from=GBP`
3. Check environment: `echo $BANXE_API_BASE` (should be `http://localhost:8090`)
4. Run specific tool with verbose logging:
   ```bash
   LOGLEVEL=DEBUG python -m banxe_mcp.server
   ```

---

## 4. Add New Tool

1. Edit `banxe_mcp/server.py` — add `@mcp_server.tool()` decorated function
2. Follow naming: `verb_noun` pattern
3. Test: `pytest tests/test_*/test_mcp_tools.py -v`
4. Update `docs/API.md` → MCP Tools Registry
5. See `.claude/rules/70-mcp-tools.md` for full checklist

---

## 5. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BANXE_API_BASE` | `http://localhost:8090` | FastAPI base URL |
| `FRANKFURTER_URL` | `http://localhost:8181` | ECB FX rates |

---

## 6. Restart After Code Change

```bash
# Kill running MCP server process (Claude Code restarts automatically)
# Or: reload Claude Code session to pick up .mcp.json changes
```

---

## 7. Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused :8090` | FastAPI not running | Start FastAPI app |
| `Connection refused :8181` | Frankfurter not running | Start docker-compose.reporting.yml |
| `Tool not found` | Tool not registered | Check @mcp_server.tool() decorator |
| `JSON decode error` | Tool returning non-string | Ensure tool returns `json.dumps(...)` |
