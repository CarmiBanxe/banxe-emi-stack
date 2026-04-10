# /deploy-check — Pre-deployment Checklist and Validation
# Source: scripts/deploy-safeguarding-gmktec.sh, scripts/deploy-recon-stack.sh, scripts/deploy-psd2-gateway.sh, scripts/deploy-sprint9.sh
# Created: 2026-04-10
# Migration Phase: 3

## Description

Pre-deployment validation checklist for the GMKtec production server.
Run these checks before executing any deploy script.

## Pre-deployment checklist

1. **Git state clean:**
   ```bash
   git status --short
   git log -1 --oneline
   ```

2. **All tests pass:**
   ```bash
   python -m pytest tests/ -x -q --timeout=30
   ```

3. **Quality gate green:**
   ```bash
   bash scripts/quality-gate.sh
   ```

4. **Environment file present:**
   ```bash
   test -f .env && echo "OK" || echo "MISSING — copy from .env.example"
   ```

5. **GMKtec reachable:**
   ```bash
   ssh gmktec 'echo OK && uptime'
   ```

6. **Docker services running on GMKtec:**
   ```bash
   ssh gmktec 'docker ps --format "{{.Names}}: {{.Status}}"'
   ```

## Deploy scripts reference

| Script | Target | What it deploys |
|--------|--------|----------------|
| `scripts/deploy-safeguarding-gmktec.sh` | Full safeguarding stack | rsync + schema + systemd timer + tests + n8n (IL-043) |
| `scripts/deploy-recon-stack.sh` | Recon stack only | Frankfurter + pgAudit + schema + dry-run (IL-010) |
| `scripts/deploy-psd2-gateway.sh` | PSD2 gateway | adorsys gateway + mock-ASPSP on ports 8888/8090 (IL-011) |
| `scripts/deploy-sprint9.sh` | Sprint 9 legacy | rsync + schema + tests + crontab (superseded by IL-043) |

## Recommended deploy order

1. `deploy-recon-stack.sh` — base infrastructure
2. `deploy-psd2-gateway.sh` — PSD2 bank connectivity
3. `deploy-safeguarding-gmktec.sh` — full stack with systemd timer

## Post-deployment verification

```bash
ssh gmktec 'systemctl list-timers banxe-recon.timer --no-pager'
ssh gmktec 'curl -sf http://localhost:8080/latest?from=GBP | head -c 100'
ssh gmktec 'curl -sf http://localhost:8888/actuator/health | head -c 100'
ssh gmktec 'docker ps --filter name=banxe --format "{{.Names}}: {{.Status}}"'
```

## Safety rules

- NEVER deploy without passing all tests first
- ALWAYS dry-run recon before enabling the systemd timer
- `.env` is NEVER synced by rsync (excluded) — secrets stay on GMKtec
- Rollback: `ssh gmktec 'cd /data/banxe/banxe-emi-stack && git checkout <previous-tag>'`
