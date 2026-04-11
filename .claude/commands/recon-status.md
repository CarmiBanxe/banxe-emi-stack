---
description: Check daily reconciliation status for all safeguarding accounts
---

Run daily reconciliation status check.

1. Check API health: `curl http://localhost:8000/health`
2. List recent recon events (if ClickHouse available):
   - Query: `SELECT recon_date, account_id, status, discrepancy FROM banxe.safeguarding_events ORDER BY recon_date DESC LIMIT 10`
3. Check for active breaches:
   - Query: `SELECT * FROM banxe.safeguarding_breaches ORDER BY detected_at DESC LIMIT 5`
4. Run recon test: `pytest tests/ -k recon -v --no-cov 2>&1 | tail -20`
