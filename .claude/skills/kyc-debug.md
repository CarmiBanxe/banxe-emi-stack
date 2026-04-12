---
name: kyc-debug
description: Debug KYC onboarding pipeline failures
context: fork
agent: Explore
allowed-tools: Bash(docker *), Bash(git *), Bash(psql *)
---

## KYC Environment Snapshot

- Git status: `!git status --short`
- Container health: `!docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "kyc|banxe" || echo "No containers"`
- Recent KYC commits: `!git log --oneline -10 -- kyc/ services/kyc/ agents/compliance/`
- KYC errors (docker logs): `!docker logs banxe-kyc --tail 100 2>&1 | grep -E "ERROR|WARN|Exception" | tail -30 || echo "Container not running"`
- Failed sessions: `!psql postgresql://banxe:banxe2025@localhost/banxe_db -c "SELECT id, user_id, step, error_code, created_at FROM kyc_sessions WHERE status='failed' AND created_at > NOW()-INTERVAL '1h' ORDER BY created_at DESC LIMIT 20" 2>/dev/null || echo "DB not available"`
- Pending verifications: `!psql postgresql://banxe:banxe2025@localhost/banxe_db -c "SELECT count(*), step FROM kyc_sessions WHERE status='pending' GROUP BY step ORDER BY count DESC" 2>/dev/null || echo "DB not available"`

## Your task

Diagnose the KYC pipeline failures shown above:

1. Identify root cause from logs and DB state
2. Check if recent code changes introduced the regression
3. Determine which onboarding steps are blocked and for how many users
4. Propose a concrete fix or rollback strategy
5. Estimate blast radius (how many users affected)
6. Check HITL gate status (`agents/compliance/orchestrator.py`)
