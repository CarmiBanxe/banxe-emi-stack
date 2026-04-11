# /mcp-status — MCP Server Health Check

Runs a full health check on the BANXE MCP server.

## Steps

### 1. Check server importability
```bash
cd /home/mmber/banxe-emi-stack && python -c "
from banxe_mcp.server import mcp_server
print('OK:', mcp_server.name)
"
```

### 2. List all registered tools
```bash
cd /home/mmber/banxe-emi-stack && python -c "
from banxe_mcp.server import mcp_server
tools = list(mcp_server._tool_manager._tools.keys())
print(f'Registered tools ({len(tools)}):')
for t in sorted(tools):
    print(f'  - {t}')
"
```

### 3. Check all tools have docstrings
```bash
cd /home/mmber/banxe-emi-stack && python -c "
import inspect
from banxe_mcp import server as srv
fns = [
    srv.get_account_balance, srv.list_accounts, srv.get_transaction_history,
    srv.get_kyc_status, srv.check_aml_alert, srv.get_exchange_rate,
    srv.get_payment_status, srv.get_recon_status, srv.get_breach_history,
    srv.get_discrepancy_trend, srv.run_reconciliation,
]
failed = [f.__name__ for f in fns if not inspect.getdoc(f)]
if failed:
    print('MISSING DOCSTRINGS:', failed)
else:
    print('OK: all tools have docstrings')
"
```

### 4. Run MCP health workflow check
```bash
cd /home/mmber/banxe-emi-stack && python -c "
from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill
result = MCPHealthSkill().check()
print(f'Status: {result[\"status\"]}')
print(f'Tools checked: {result[\"tools_checked\"]}')
print(f'Failed: {result[\"tools_failed\"]}')
print(f'Checked at: {result[\"checked_at\"]}')
"
```

### 5. Run MCP tests
```bash
cd /home/mmber/banxe-emi-stack && pytest tests/ -k mcp -v --no-cov 2>&1 | tail -30
```

## Expected output (healthy)
```
OK: BANXE EMI AI Bank
Registered tools (11): ...
OK: all tools have docstrings
Status: healthy | Tools checked: 11 | Failed: []
tests/test_mcp_server.py ... PASSED
tests/test_mcp_health_workflow.py ... PASSED
```
