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

## Alignment — canon test API (2026-06-19, Channel C)
Aligned InMemory ports to canon tests (tests = spec; tests unchanged). Files: fx_exposure_port.py, liquidity_forecast_port.py.
- FXExposurePort: `InMemoryFXExposurePort(positions)` seeds via constructor; `FXExposureView` → `total_exposure_gbp`, `positions: list`, empty `as_of="1970-01-01"`.
- LiquidityForecastPort: `InMemoryLiquidityForecastPort(inputs, current_position, inputs_raises, position_raises)`; `get_current_position` default `Decimal("0")`; missing-inputs error message matches "No forecast inputs".
- Preserved: frozen value objects, async, Decimal (I-01), read-only invariants. NOSTRO port unchanged.
- Verify: `ruff check services/treasury` clean; `pytest tests/test_treasury/test_fx_exposure_port.py tests/test_treasury/test_liquidity_forecast_port.py` = 13 passed.
- Out of scope (pre-existing, NOT touched): `tests/test_treasury/test_nostro_recon_port.py::test_result_carries_as_of_from_balance` (NOSTROReconPort lookup-key bug) — separate follow-up per this brief's "do not touch nostro".
