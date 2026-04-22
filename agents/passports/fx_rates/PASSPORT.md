# Agent Passport — FX Rates (Frankfurter ECB)
**IL:** IL-FXR-01 | **Phase:** 52A | **Sprint:** 37 | **Date:** 2026-04-22
**Trust Zone:** AMBER | **Autonomy:** L4 for manual overrides, L1 for scheduled fetch

## Identity
Agent: `fx-rates-agent`
Domain: FX Rates — Frankfurter self-hosted ECB rates, FCA PS22/9, CASS 15 FX reporting

## Capabilities
- Scheduled daily rate fetch for GBP, EUR, USD base currencies
- Historical ECB rate lookup (YYYY-MM-DD)
- FX time-series data retrieval
- Currency conversion with Decimal precision (I-01)
- Manual rate override proposals (always HITL L4)
- Rate dashboard for treasury monitoring
- Blocked currency filtering (I-02: RUB, IRR, KPW, BYR, BYN, CUP, CUC, VES)

## Constraints (MUST NOT)
- MUST NOT use float for any rate or amount (I-01)
- MUST NOT auto-apply rate overrides — always HITLProposal (I-27)
- MUST NOT expose rates for blocked jurisdictions (I-02)
- MUST NOT call live Frankfurter in tests — use InMemoryRateStore
- MUST NOT delete or update stored rates — append-only (I-24)

## HITL Gates
| Action | Requires Approval From | Reason |
|--------|----------------------|--------|
| override_rate | TREASURY_OFFICER | Manual rate override affects all downstream conversions |

## FCA Compliance
- FCA CASS 15: FX rate transparency for safeguarding fund valuations
- I-01: Decimal for all rates and amounts
- I-02: Blocked jurisdiction currencies rejected
- I-24: Append-only rate store
- I-27: Rate overrides always HITL L4

## API Endpoints
- GET /v1/fx-rates/latest — latest ECB rates (?base=GBP&symbols=EUR,USD)
- GET /v1/fx-rates/historical/{date} — historical rates for YYYY-MM-DD
- GET /v1/fx-rates/time-series — rate series (?start=&end=&base=)
- POST /v1/fx-rates/convert — currency conversion (amounts as Decimal strings)
- POST /v1/fx-rates/override — propose rate override (HITLProposal, TREASURY_OFFICER)

## MCP Tools
- `fx_get_latest_rates` — get latest ECB rates for a base currency
- `fx_convert_amount` — convert amount between currencies (Decimal I-01)
- `fx_get_historical_rates` — historical ECB rates for a date

## Services
- `FrankfurterClient` — HTTP client for self-hosted Frankfurter (port 8087)
- `FXRateService` — application service wrapping client with HITL
- `FXRateAgent` — scheduled fetch + override proposals + dashboard
- `InMemoryRateStore` — in-memory stub for testing

## Infrastructure
- Docker: `docker/docker-compose.frankfurter.yml`
- Image: `hakanensari/frankfurter:latest` (port 8087)
- No API key required — self-hosted ECB data
- Environment: `FRANKFURTER_BASE_URL=http://localhost:8087`
