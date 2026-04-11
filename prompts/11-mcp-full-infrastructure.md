# 11 -- MCP Server Full Infrastructure -- Claude Code Prompt

## Created: 2026-04-11 | IL-MCP-01 | Migration Phase: 4

## Context

You are working on **banxe-emi-stack** (branch `refactor/claude-ai-scaffold`).
Task: bring MCP Server feature (`banxe_mcp/`) to 100% Infrastructure Utilization Checklist compliance.

## WHAT ALREADY EXISTS

Code:
- `banxe_mcp/server.py` (448 lines, 17.4 KB) -- FastMCP server with 10+ tools
- `banxe_mcp/__init__.py` -- package init
- `banxe_mcp/__main__.py` -- `python -m banxe_mcp` entry point
- `banxe_mcp/tools.py` -- tool definitions (if exists)
- `.mcp.json` -- LucidShark MCP integration config
- MCP tools include: get_recon_status, get_breach_history, get_discrepancy_trend, plus original Phase 0 read-only tools

Infra available:
- `.claude/rules/infrastructure-utilization.md` -- CANON checklist rule
- `.claude/CLAUDE.md` -- Infrastructure Utilization Checklist
- `.semgrep/banxe-rules.yml` -- custom semgrep rules
- `agents/compliance/soul/` -- 9 soul files
- `agents/compliance/orchestrator.py` -- skill registration
- `agents/compliance/workflows/` -- workflow definitions
- `.ai/registries/agent-map.md` -- agent registry
- `n8n/workflows/` -- n8n automations
- `infra/grafana/dashboards/` -- Grafana dashboards
- `dbt/models/` -- dbt analytics models
- `docker/docker-compose*.yml` -- Docker services
- `.claude/commands/` -- slash commands
- `.claude/hooks/` -- post-edit-scan, pre-commit-q

## CANONICAL RULES

1. Decimal-only -- NEVER float for money
2. Protocol DI -- all dependencies via typing.Protocol
3. InMemory stubs -- every Protocol has in-memory implementation
4. After every change: `pytest tests/ -k mcp -x`
5. INFRASTRUCTURE CHECKLIST -- must pass ALL 15 points

## GAPS TO FIX (9 items)

### 1. Semgrep: MCP-specific rules
Add to `.semgrep/banxe-rules.yml`:
- `banxe-mcp-tool-must-have-docstring` -- every @mcp_server.tool function must have a docstring
- `banxe-mcp-no-raw-exception` -- MCP tools must not raise raw Exception, use typed errors

### 2. Claude Commands: `/mcp-status`
Create `.claude/commands/mcp-status.md`:
- Check MCP server importability: `python -c "from banxe_mcp.server import mcp_server; print('OK:', mcp_server.name)"`
- List registered tools: `python -c "from banxe_mcp.server import mcp_server; print([t.name for t in mcp_server._tools.values()])"`
- Run MCP tests: `pytest tests/ -k mcp -v --no-cov 2>&1 | tail -20`

### 3. AI Agent Soul: MCP Server Agent
Create `agents/compliance/soul/mcp_server_agent.soul.md`:
- Role: MCP Server management agent
- Responsibilities: health monitoring, tool registry validation, usage metrics
- Personality: infrastructure guardian, ensures all tools are documented and tested
- Triggers: startup health check, tool registration changes, error rate spikes

### 4. Agent Workflow: MCP Health Monitoring
Create `agents/compliance/workflows/mcp_health_workflow.py`:
- Step 1: Import banxe_mcp.server, verify all tools load
- Step 2: Check each tool has docstring and type hints
- Step 3: Run smoke test on each tool with mock data
- Step 4: Report results to ClickHouse banxe.mcp_health_events
- Schedule: on startup + every 6 hours

### 5. Orchestrator Registration
Update `agents/compliance/orchestrator.py`:
- Register MCPHealthSkill
- MCPHealthSkill.check() -- validates all MCP tools are functional
- MCPHealthSkill.list_tools() -- returns tool inventory

### 6. n8n Workflow: MCP Monitoring
Create `n8n/workflows/mcp-health-monitor.json`:
- Trigger: webhook from MCP health workflow
- If error_count > 0: Slack #infra-alerts
- Daily summary: tool call count, error rate, avg latency
- Telegram notification on critical failures

### 7. Docker: MCP as service
Update `docker/docker-compose.yml` (or create `docker/docker-compose.mcp.yml`):
- Service `banxe-mcp`:
  - `command: python -m banxe_mcp --transport sse`
  - `ports: ["8100:8100"]`
  - `healthcheck: python -c "from banxe_mcp.server import mcp_server; print('healthy')"`
  - `depends_on: [clickhouse, postgres]`
  - `env_file: .env`

### 8. Grafana: MCP Dashboard
Create `infra/grafana/dashboards/mcp-server.json`:
- Panel 1: Tool call count per tool (bar chart)
- Panel 2: Error rate over time (line chart)
- Panel 3: Average response time per tool (heatmap)
- Panel 4: Active connections (stat)
- Panel 5: Tool registry inventory (table)
- Datasource: ClickHouse (banxe.mcp_tool_events)

### 9. Tests: MCP Server Tests
Create `tests/test_mcp_server.py`:
- test_server_imports -- `from banxe_mcp.server import mcp_server`
- test_all_tools_have_docstrings -- iterate tools, assert __doc__
- test_get_recon_status_tool -- mock dependencies, call tool
- test_get_breach_history_tool -- mock dependencies, call tool
- test_get_discrepancy_trend_tool -- mock dependencies, call tool
- test_tool_error_handling -- ensure typed errors not raw Exception
- test_server_name -- assert mcp_server.name == "BANXE EMI AI Bank"

Create `tests/test_mcp_health_workflow.py`:
- test_health_check_all_tools_pass
- test_health_check_detects_broken_tool

### ALSO: ClickHouse migration for MCP metrics
Create `infra/clickhouse/migrations/005_create_mcp_tool_events.sql`:
- tool_name String
- called_at DateTime
- duration_ms UInt32
- status String (OK/ERROR)
- error_message Nullable(String)
- caller_agent String

### ALSO: dbt model for MCP analytics
Create `dbt/models/mcp/mcp_tool_usage.sql`:
- Daily tool call counts by tool_name
- Error rate percentage
- Average duration

### ALSO: AI Registry
Update `.ai/registries/agent-map.md`:
- Add MCP Server Agent entry with capabilities and health endpoint

## EXECUTION ORDER

1. Tests first -- `tests/test_mcp_server.py` (TDD)
2. Semgrep rules
3. Claude Command `/mcp-status`
4. Soul file + Orchestrator registration
5. Agent workflow + n8n
6. ClickHouse migration + dbt model
7. Docker service
8. Grafana dashboard
9. AI Registry update
10. Run full checklist verification

Commit messages:
- `test(mcp): add MCP server tests + health workflow tests [IL-MCP-01]`
- `feat(mcp): full infrastructure integration -- semgrep, soul, orchestrator, n8n, docker, grafana, dbt [IL-MCP-01]`
- `docs(mcp): update AI registry + API docs for MCP server [IL-MCP-01]`

## INFRASTRUCTURE CHECKLIST (must be filled before done)

```
INFRASTRUCTURE CHECKLIST -- MCP Server (banxe_mcp/)
[ ] LucidShark scan clean
[ ] Semgrep rules added (mcp-tool-docstring, mcp-no-raw-exception)
[ ] Claude Rules coverage
[ ] Claude Hooks integration
[ ] Claude Commands created (/mcp-status)
[ ] AI Agent Soul file (mcp_server_agent.soul.md)
[ ] Agent Workflow (mcp_health_workflow.py)
[ ] Orchestrator registration (MCPHealthSkill)
[ ] MCP Server tools -- self (already exists)
[ ] AI Registry updated
[ ] n8n Workflows (mcp-health-monitor.json)
[ ] Docker service (banxe-mcp in docker-compose)
[ ] dbt models (mcp/mcp_tool_usage.sql)
[ ] Grafana dashboard (mcp-server.json)
[ ] Tests passing (test_mcp_server.py + test_mcp_health_workflow.py)
```

## AFTER COMPLETION

Print filled checklist and run:
`pytest tests/ -k mcp -v --tb=short`
