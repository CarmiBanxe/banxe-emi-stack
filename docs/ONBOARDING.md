# ONBOARDING — Banxe EMI Analytics Stack

**Welcome.** This document gets a new engineer from zero to running in one session.

**Prerequisites:** Python 3.12+, git, SSH access to GMKtec (192.168.0.72).

---

## 1. Clone and Setup

```bash
# Clone (request access from CEO)
git clone git@github.com:CarmiBanxe/banxe-emi-stack.git
cd banxe-emi-stack

# Install dependencies (no requirements.txt — lightweight by design)
pip install httpx pytest pytest-cov pytest-asyncio ruff

# Optional heavy deps (only needed for production run)
pip install clickhouse-driver weasyprint
```

---

## 2. Run Tests — Verify Everything Works

```bash
python3 -m pytest tests/ -v
# Expected: 75/75 PASS in ~0.1s (no external dependencies needed)

bash scripts/quality-gate.sh --fast
# Expected: ✅ PASS
```

If any test fails before you've changed anything → report to CTIO immediately.

---

## 3. Architecture in 5 Minutes

```
CEO / Compliance Officer
        │
        ▼
  daily-recon.sh (cron 07:00 Mon-Fri)
        │
        ▼
  midaz_reconciliation.py  ← orchestrates everything
        │
        ├── MidazLedgerAdapter  ← fetches balances from Midaz CBS (:8095)
        ├── StatementFetcher    ← reads CAMT.053 XML from /data/banxe/statements/
        ├── ReconciliationEngine ← compares, classifies MATCHED/DISCREPANCY/PENDING
        ├── ClickHouseReconClient ← writes to banxe.safeguarding_events (I-24)
        ├── _fire_alerts()      ← n8n webhook → Slack (CASS 7.15.29R)
        └── BreachDetector      ← streak ≥3 days → safeguarding_breaches + FCA alert
```

**Three invariants you must never break:**
- **I-05:** `Decimal` only for money — never `float`
- **I-24:** ClickHouse audit tables are append-only — no DELETE/UPDATE
- **I-08:** ClickHouse TTL ≥ 5 years — never reduce

---

## 4. Key Files Map

```
banxe-emi-stack/
├── services/
│   ├── config.py                    ← ALL env vars centralised here (read this first)
│   ├── recon/
│   │   ├── reconciliation_engine.py ← core domain logic (MATCHED/DISCREPANCY/PENDING)
│   │   ├── breach_detector.py       ← CASS 15.12 breach escalation
│   │   ├── clickhouse_client.py     ← ClickHouse client + InMemoryReconClient (tests)
│   │   ├── midaz_reconciliation.py  ← daily pipeline CLI entry point
│   │   ├── statement_fetcher.py     ← reads bank statements (CSV + CAMT.053)
│   │   └── bankstatement_parser.py  ← parses CAMT.053 / MT940
│   ├── payment/
│   │   ├── payment_port.py          ← PaymentRailPort interface + dataclasses
│   │   ├── mock_payment_adapter.py  ← MockAdapter (default, no API key needed)
│   │   ├── modulr_client.py         ← Modulr REST adapter (FPS + SEPA)
│   │   ├── payment_service.py       ← PaymentService: orchestration + audit
│   │   └── webhook_handler.py       ← FastAPI router for Modulr webhooks
│   └── reporting/
│       └── fin060_generator.py      ← FIN060 PDF generator (WeasyPrint)
├── tests/                           ← 75 unit tests, no external deps
├── scripts/
│   ├── daily-recon.sh               ← cron: 0 7 * * 1-5
│   ├── monthly-fin060.sh            ← cron: 0 8 1 * *
│   └── quality-gate.sh              ← run before every commit
├── dbt/                             ← staging → safeguarding → fin060 models
├── docs/
│   ├── RUNBOOK.md                   ← incident playbooks
│   ├── ONBOARDING.md                ← you are here
│   └── API.md                       ← public interfaces
└── CHANGELOG.md                     ← version history
```

---

## 5. Environment Variables

All variables are in `/data/banxe/.env` on GMKtec. See `services/config.py` for defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `CLICKHOUSE_PORT` | `9000` | ClickHouse port |
| `CLICKHOUSE_DB` | `banxe` | Database name |
| `MIDAZ_BASE_URL` | `http://localhost:8095` | Midaz CBS URL |
| `MIDAZ_TOKEN` | `` | Midaz auth token (empty = no auth) |
| `STATEMENT_DIR` | `/data/banxe/statements` | CAMT.053 XML directory |
| `SAFEGUARDING_OPERATIONAL_IBAN` | `` | Operational account IBAN |
| `SAFEGUARDING_CLIENT_FUNDS_IBAN` | `` | Client funds IBAN |
| `N8N_WEBHOOK_URL` | `` | n8n webhook URL for alerts |
| `PAYMENT_ADAPTER` | `mock` | `mock` or `modulr` |
| `MODULR_API_KEY` | `` | Modulr API key (sandbox or prod) |
| `FIN060_OUTPUT_DIR` | `/data/banxe/reports/fin060` | PDF output directory |

**Never commit `.env` to git.** Store secrets on GMKtec only.

---

## 6. Running a Dry-Run Reconciliation

```bash
# Dry run — no ClickHouse writes, no alerts
python3 -m services.recon.midaz_reconciliation --dry-run --date 2026-04-07

# With JSON output
python3 -m services.recon.midaz_reconciliation --dry-run --date 2026-04-07 --json
```

Expected output in sandbox (Midaz running, no real bank statements):
```json
{"overall_status": "PENDING", "matched": 0, "discrepancy": 0, "pending": 2}
```

---

## 7. Making a Change — Checklist

Before every commit:
```bash
python3 -m ruff check services/ tests/     # must be 0 issues
python3 -m pytest tests/ -q                # must be 75/75
bash scripts/quality-gate.sh --fast        # must be ✅ PASS
```

Commit message format:
```
feat(il-NNN): short description

- bullet points of what changed
- FCA rule if applicable

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

The quality gate hook will automatically block `git commit` if gate fails.

---

## 8. FCA Context (Why This Exists)

Banxe Limited is seeking FCA EMI authorisation. **Deadline: 7 May 2026.**

Key regulatory requirements implemented in this stack:
- **CASS 7.15** — daily reconciliation of safeguarded client funds
- **CASS 15 / PS25/12** — monthly FIN060 return to FCA RegData
- **CASS 15.12** — breach notification within 1 business day if discrepancy persists ≥ 3 days
- **FCA I-24** — immutable audit trail (ClickHouse append-only, TTL 5Y)

When in doubt about a change → ask: "Does this make the FCA audit trail less reliable?" If yes, don't do it.
