# Quality Debt — legacy bandit HIGH findings (2026-07-27)

Pre-commit gate scans STAGED files only (guards new code). These pre-existing repo-wide
bandit HIGH findings are tracked here as debt, to be triaged separately (not per-commit blockers):

1. services/agents/recorders.py:255 — B608 hardcoded_sql_expressions (possible SQL injection).
   ACTION: verify parameterisation; if string-built, refactor to bound params. Owner: Eng.
2. services/watchdog/prometheus_exporter.py:148 — B104 hardcoded_bind_all_interfaces (0.0.0.0 bind).
   ACTION: confirm intended (container metrics) or restrict bind; add # nosec with justification if OK. Owner: Platform/SRE.

Until triaged, they do NOT block commits, because the gate is staged-scoped. When a commit
TOUCHES either file, the staged-scan will flag it and require resolution at that point.
