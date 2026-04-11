# Reporting Rules — BANXE AI BANK
# Rule ID: 90-reporting | Load order: 90
# Created: 2026-04-11 | IL-SK-01

## Reproducibility

- Every report must be reproducible from source data alone.
- SQL queries, dbt models, and Python scripts that generate reports must be version-controlled.
- No manual edits to report output files — reports are always generated, never hand-edited.

## Data Lineage

- Every report field must have a documented source of truth:
  `field → dbt model → source table → raw data origin`.
- Breaking the lineage chain (e.g., joining in an undocumented temp table) is a compliance risk.
- dbt model descriptions and column-level documentation are mandatory for FIN060 models.

## Date Ranges and Timezones

- All financial reports use **UTC** internally; convert to local timezone only for display.
- Report period (start_date, end_date) must be stated explicitly, including whether boundaries
  are inclusive or exclusive.
- Cutoff time for daily reports: **23:59:59 UTC** (state explicitly in every report header).
- FCA regulatory submissions follow FCA calendar (business days, UK timezone for deadlines).

## Historical Comparability

- Changing a report's logic mid-period requires a note documenting the change date and effect.
- Restatements must be approved by CFO/MLRO and logged in the audit trail.
- dbt models use `incremental` strategy with `unique_key` to prevent double-counting on reruns.

## Source of Truth per Field

| Report | Amount source | Balance source | FX source |
|--------|--------------|---------------|-----------|
| FIN060a/b | Midaz ledger | Midaz get_balance | Frankfurter ECB |
| Daily recon | Midaz ledger | Blnk positions | — |
| AML reports | ClickHouse events | — | Frankfurter ECB |

## References

- FIN060 generator: `services/reporting/fin060_generator.py`
- dbt models: `dbt/models/marts/fin060/`
- FX rates: `services/providers/fx/frankfurter_client.py`
