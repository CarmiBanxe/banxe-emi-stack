# IL-172 — CFO Treasury & Forecast Ports

- anchor: IL-172-CFO-TREASURY-FORECAST-PORTS-2026-06-09
- adr: ADR-078
- channel: C (operator-driven terminal session, per #526 gate; PR #521 evidence)
- scope: BANXE-only

## Deliverable (first write)
Three read-only hexagonal ports + InMemory impls (no live adapters, I-10-safe; Decimal, I-01):
- D1 FXExposurePort — get_exposure / get_total_exposure
- D2 NOSTROReconPort — get_nostro_balances / reconcile
- D3 LiquidityForecastPort — get_forecast_inputs / get_current_position

## Invariants
Read/aggregate only. No trade execution, transfer initiation, model runs, or state mutation.
Consumers (TreasuryAgent/ForecastAgent) and >£100k CFO sign-off HITL land in a follow-up shard.
