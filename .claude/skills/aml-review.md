---
name: aml-review
description: Review pending AML alerts and transaction monitoring events
context: fork
agent: Explore
allowed-tools: Bash(psql *), Bash(git *), Bash(docker *)
---

## Live AML Context

- Current branch: `!git branch --show-current`
- Pending alerts: `!psql postgresql://banxe:banxe2025@localhost/banxe_db -c "SELECT id, transaction_id, rule_id, risk_score, created_at FROM aml_alerts WHERE status='pending' ORDER BY risk_score DESC LIMIT 30" 2>/dev/null || echo "DB not available"`
- Rule triggers (last 24h): `!psql postgresql://banxe:banxe2025@localhost/banxe_db -c "SELECT rule_id, count(*) as hits FROM monitoring_events WHERE created_at > NOW()-INTERVAL '24h' GROUP BY rule_id ORDER BY hits DESC" 2>/dev/null || echo "DB not available"`
- Recent code changes to monitoring: `!git log --oneline -15 -- services/fraud/ aml/ monitoring/ agents/compliance/`
- Running AML services: `!docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -E "aml|monitor|compliance|banxe" || echo "No containers"`
- Compliance tests: `!pytest tests/compliance/ --tb=no -q 2>&1 | tail -3 || echo "No compliance tests found"`

## Your task

Analyze the pending AML alerts above. For each alert:

1. Identify the triggered rule and its risk level
2. Check if recent code changes could have caused false positives
3. Suggest whether the alert should be escalated, dismissed, or needs manual review
4. Flag any patterns that indicate systemic issues vs isolated events
5. Check against BANXE compliance architecture (services/compliance_kb/)

Output a structured report with severity classification (HIGH / MEDIUM / LOW).
Reference: FCA CASS 15 P0, EU AML Directive 6.
