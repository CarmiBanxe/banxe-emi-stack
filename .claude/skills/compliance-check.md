---
name: compliance-check
description: FCA/EU EMI compliance status snapshot before deployment
context: fork
agent: Analyze
allowed-tools: Bash(git *), Bash(gh *), Bash(curl *), Bash(cat *), Bash(pytest *)
---

## Compliance State

- Branch & last commit: `!git log --oneline -1`
- Open compliance issues: `!gh issue list --label compliance,fca,emi --state open --json number,title,labels 2>/dev/null || echo "gh CLI not configured"`
- Config changes (last 7 days): `!git diff HEAD~7 -- config/ compliance/ rules/ 2>/dev/null | head -50`
- Compliance tests: `!pytest tests/compliance/ --tb=no -q 2>&1 | tail -5 || echo "No compliance tests"`
- Compliance KB status: `!cat config/compliance_notebooks.yaml 2>/dev/null | head -20 || echo "Not found"`
- LexisNexis integration: `!curl -sf http://localhost:8080/health/lexisnexis 2>/dev/null || echo "Service unreachable"`
- Recent compliance commits: `!git log --oneline -10 -- services/compliance_kb/ agents/compliance/ compliance/`
- MLRO agent config: `!cat agents/compliance/mlro_agent.py 2>/dev/null | head -15 || echo "Not found"`
- Sanctions check: `!cat services/fraud/fraud_aml_pipeline.py 2>/dev/null | head -10 || echo "Not found"`

## Your task

Review the compliance posture of the current codebase:

1. Check if any open compliance issues block deployment
2. Identify config changes that may affect FCA/EMI regulatory requirements
3. Verify compliance tests are passing (58/58 minimum)
4. Check MLRO agent and AML pipeline integrity
5. Verify LexisNexis and sanctions check integrations
6. Output a **GO / NO-GO** deployment recommendation with justification

Reference: FCA CASS 15, EU EMI Directive, Consumer Duty FCA PS22/9.
