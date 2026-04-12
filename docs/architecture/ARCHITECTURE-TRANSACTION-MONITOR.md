# Architecture: Realtime Transaction Monitoring Agent

**IL:** IL-071 (IL-RTM-01) | **Created:** 2026-04-12
**FCA rules:** MLR 2017 s.2.1, FATF Recommendation 10, FCA FG21/7

---

## Overview

AML pipeline for realtime scoring of every transaction event. Produces explainable alerts and routes to Marble case management.

## Component Map

```
TransactionEvent (Decimal, I-01)
        ↓
TransactionParser (validation + ParseError)
        ↓
FeatureExtractor (10 features)
        ↓
RiskScorer (composite: rules 40% + ML 30% + velocity 30%)
├── RuleEngine → JubePort (InMemoryJubePort / HTTPJubePort)
├── MLModel → MLModelPort (IsolationForest, deferred import)
└── InMemoryVelocityTracker (sliding windows: 1h/24h/7d)
        ↓
AlertGenerator (score → AlertSeverity)
        ↓
ExplanationEngine (KB citations + regulation refs)
        ↓
AlertRouter → Marble (case mgmt) + MLRO notifications
        ↓
InMemoryAlertStore → ClickHouse audit (I-24)
```

## Risk Scoring

| Factor | Weight | Source |
|--------|--------|--------|
| Rule engine score | 40% | Jube rules (InMemoryJubePort in test) |
| ML anomaly score | 30% | IsolationForest (deferred) |
| Velocity score | 30% | Sliding window Redis (InMemory in test) |

| Severity | Threshold | Auto-action |
|----------|-----------|-------------|
| CRITICAL | ≥ 0.90 | → Marble ESCALATED + MLRO notification |
| HIGH | ≥ 0.75 | → Marble REVIEWING + analyst notification |
| MEDIUM | ≥ 0.50 | → analyst REVIEWING |
| LOW | < 0.50 | AUTO_CLOSED |

## Key Invariants

- **I-01:** `TransactionEvent.amount` is `Decimal` — never float
- **I-02:** Jurisdictions RU/BY/IR/KP/CU/MM/AF/VE/SY → score forced to 1.0 (hard block)
- **I-04:** Cumulative 24h spend ≥ £10,000 → EDD flag
- **I-24:** All alerts append to ClickHouse `banxe.aml_events`
- **I-27:** CRITICAL alert closure requires `reviewer_notes` (HITL gate)

## 10 Extracted Features

amount_gbp, amount_deviation_from_avg, jurisdiction_risk, counterparty_risk, is_crypto, is_round_number, velocity_1h, velocity_24h, velocity_7d, hour_of_day

## Ports (Protocol DI)

| Port | Production | Test stub |
|------|-----------|---------|
| `StreamPort` | Kafka/Redis stream consumer | `InMemoryStreamPort` |
| `JubePort` | `HTTPJubePort` | `InMemoryJubePort` |
| `MLModelPort` | IsolationForest (sklearn) | `InMemoryMLModelPort` |
| `AlertStorePort` | ClickHouse | `InMemoryAlertStore` |
| `MarblePort` | Marble REST API | `InMemoryMarblePort` |
| `KBPort` | Compliance KB service | `InMemoryKBPort` |

## API Endpoints

```
GET  /monitor/health
POST /monitor/score
GET  /monitor/alerts
GET  /monitor/alerts/{id}
PATCH /monitor/alerts/{id}
GET  /monitor/velocity/{customer_id}
GET  /monitor/metrics
POST /monitor/backtest
```

## MCP Tools (5)

`monitor_score_transaction`, `monitor_get_alerts`, `monitor_get_alert_detail`, `monitor_get_velocity`, `monitor_dashboard_metrics`

## Files

```
services/transaction_monitor/
├── models/           — TransactionEvent, RiskScore, AMLAlert, AlertSeverity
├── scoring/          — FeatureExtractor, InMemoryVelocityTracker, RuleEngine, RiskScorer
├── alerts/           — ExplanationEngine, AlertGenerator, AlertRouter
├── consumer/         — TransactionParser, EventConsumer
├── store/            — AlertStorePort, InMemoryAlertStore
└── config.py
api/routers/transaction_monitor.py
docker/docker-compose.transaction-monitor.yml
tests/test_transaction_monitor/ (105 tests)
```
