---
# Infrastructure Utilization Rule — BANXE AI BANK

WHEN implementing any feature that introduces new functionality:

ALWAYS check these integration points BEFORE declaring done:
1. LucidShark scan must pass
2. Semgrep custom rules must cover new patterns (especially financial invariants)
3. MCP Server must expose new functionality as tools if callable by AI agents
4. AI Agent soul files must exist for any new compliance/analysis skill
5. Agent orchestrator must register new skills
6. n8n workflows must be created/updated for any new notification or automation
7. Grafana dashboards must visualize any new data in ClickHouse
8. dbt models for any new analytical data
9. Docker compose must include all new services

NEVER declare a feature complete without:
- pytest tests/ -k <feature> -v passing
- Infrastructure Checklist printed with status for each point

This rule is CANON. Violation = P1 defect.
---
