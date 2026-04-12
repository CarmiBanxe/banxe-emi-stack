# FCA CASS 15 Compliance Controls — Banxe EMI

**Regulation:** FCA CASS 15 (PS25/12 — effective date TBD)
**P0 Deadline:** 7 May 2026
**Owner:** MLRO / CFO
**Last reviewed:** 2026-04-12 (IL-RETRO-02)

---

## Control Matrix

| Control ID | Regulatory Ref | Requirement | Implementation | Status |
|------------|---------------|-------------|----------------|--------|
| CASS-01 | CASS 15.2.2R | Segregation: client funds in separate accounts | `safeguarding_accounts.account_type = "client_funds"` | ✅ |
| CASS-02 | CASS 15.7 | Daily reconciliation | `ReconciliationService` + `scripts/daily-recon.sh` (07:00 UTC) | ✅ |
| CASS-03 | CASS 15.12.4R | Monthly FIN060 return by 15th | `FIN060Generator` + `RegDataReturnService` + `scripts/monthly-fca-return.sh` | ✅ (stub: needs FCA_REGDATA_API_KEY) |
| CASS-04 | CASS 15.12.4R | Breach notification within 1 business day | `BreachService` (≥3 day DISCREPANCY → `POST /v1/breaches/report`) | ✅ |
| CASS-05 | MLR 2017 s.40 | 5-year audit trail retention | ClickHouse `banxe.safeguarding_events` (TTL 5yr, I-08) | ✅ |
| CASS-06 | PS25/12 | Safeguarding return in FIN060 format | `services/reporting/fin060_generator.py` (WeasyPrint PDF) | ✅ |
| CASS-07 | CASS 15.3 | Acknowledgement letters from banks | Manual — CEO action required | ⏳ |
| CASS-08 | CASS 15.8 | Third-party agreements | Manual — legal review required | ⏳ |

---

## Daily Reconciliation Flow

```
07:00 UTC (Mon-Fri, cron)
    ↓
scripts/daily-recon.sh
    ↓
ReconciliationEngine.reconcile(today)
    ↓
Midaz balance ↔ CAMT.053 bank statement
    ↓
ReconResult: MATCHED / DISCREPANCY / PENDING
    ↓ if DISCREPANCY
BreachDetector.check_and_escalate()
    ↓ if days_outstanding >= 3
BreachService → safeguarding_breaches + FCA notification
    ↓
ClickHouse: safeguarding_events (append-only, I-24)
```

---

## Monthly FIN060 Flow

```
1st of month (cron via scripts/monthly-fca-return.sh)
    ↓
dbt run --models fin060_monthly
    ↓
FIN060Generator.generate_fin060(period_start, period_end)
    → WeasyPrint PDF → /data/banxe/reports/fin060/FIN060_YYYYMM.pdf
    ↓
RegDataReturnService.run_monthly_return()
    → [STUB: requires FCA_REGDATA_API_KEY]
    ↓ CFO review (L4 gate per agent-authority.md)
RegData API submission
```

**CEO ACTION REQUIRED:** Set `FCA_REGDATA_API_KEY` in `.env` to enable live RegData submission.

---

## AML Controls (MLR 2017)

| Control | Threshold | Implementation |
|---------|-----------|----------------|
| EDD trigger (individual) | ≥ £10,000 cumulative 24h | `InMemoryVelocityTracker` (I-04) |
| EDD trigger (corporate) | ≥ £50,000 cumulative 24h | `InMemoryVelocityTracker` (I-04) |
| Hard-block jurisdictions | RU/BY/IR/KP/CU/MM/AF/VE/SY | `RiskScorer` (I-02, score=1.0) |
| FATF greylist | 23 countries | `aml_thresholds.py` (I-03) |
| SAR filing | POCA 2002 s.330 | `sar_service.py` (L4: MLRO only) |

---

## Key Evidence Artefacts

| Artefact | Location | Retention |
|----------|----------|-----------|
| Daily recon results | `banxe.safeguarding_events` (ClickHouse) | 5 years |
| Breach records | `safeguarding_breaches` (PostgreSQL) | 5 years |
| FIN060 PDFs | `/data/banxe/reports/fin060/` | 5 years |
| AML alerts | `banxe.aml_events` (ClickHouse) | 5 years |
| SAR filings | `services/aml/sar_service.py` | 5 years |
| Audit trail | pgAudit → `services/config/pgaudit.conf` | 5 years |

---

## References

- COMPLIANCE-MATRIX.md: `banxe-architecture/docs/COMPLIANCE-MATRIX.md`
- Regulatory: FCA CASS 15, PS25/12, MLR 2017, POCA 2002 s.330
- Technical: `docs/architecture/ARCHITECTURE-SAFEGUARDING-ENGINE.md`
- Runbook: `docs/runbooks/safeguarding-engine.md`
