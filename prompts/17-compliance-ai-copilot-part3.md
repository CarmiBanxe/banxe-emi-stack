# Prompt 17 Part 3/3 — Realtime Transaction Monitoring Agent

> **Feature**: Agentic Transaction Monitoring + Explainable AML Alerts
> **Ticket**: IL-RTM-01 | **Branch**: refactor/claude-ai-scaffold
> **Depends on**: Prompt 17 Part 1 (KB), Part 2 (Experiment Copilot)
> **All tools**: Open-source or free tier

---

## Context

Realtime transaction monitoring agent that consumes event streams,
applies ML risk scoring, generates explainable alerts, and routes
cases to human reviewers. Integrates with Jube (fraud rules engine),
Marble (case management), and the Compliance KB for regulation lookups.
Targets: reduce false positives from 94% to <35%, improve SAR yield
from 6.5% to 20%, meet 24h review SLA at 95%.

## Architecture

```
+-------------------+     +--------------------+     +------------------+
| Event Stream       |---->| Risk Scoring       |---->| Alert Generator  |
| (RabbitMQ/Redis)   |     | (ML + Rules)       |     | (Explainable)    |
+-------------------+     +--------------------+     +------------------+
        |                         |                          |
        v                         v                          v
+-------------------+     +--------------------+     +------------------+
| Transaction Parser |     | Jube Rules Engine  |     | Marble Cases     |
| (Pydantic models)  |     | (existing :5001)   |     | (existing :5002) |
+-------------------+     +--------------------+     +------------------+
        |                         |                          |
        v                         v                          v
+-------------------+     +--------------------+     +------------------+
| Compliance KB      |     | ClickHouse Store   |     | Grafana Dashboard|
| (Part 1 MCP)       |     | (analytics)        |     | (monitoring)     |
+-------------------+     +--------------------+     +------------------+
```

## Phase 1 — Transaction Event Model + Stream Consumer

### 1.1 Directory structure

```
services/transaction_monitor/
  __init__.py
  consumer/
    __init__.py
    event_consumer.py      # RabbitMQ/Redis stream consumer
    transaction_parser.py  # Parse raw events to Pydantic models
  scoring/
    __init__.py
    risk_scorer.py         # ML risk scoring pipeline
    rule_engine.py         # Integration with Jube rules
    velocity_tracker.py    # Redis velocity checks
    feature_extractor.py   # Extract ML features from transactions
  alerts/
    __init__.py
    alert_generator.py     # Create explainable alerts
    alert_router.py        # Route to Marble / human reviewer
    explanation_engine.py  # Generate human-readable explanations
  models/
    __init__.py
    transaction.py         # Transaction Pydantic models
    alert.py               # Alert models with explanations
    risk_score.py          # Risk score with factor breakdown
  config.py
```

### 1.2 Transaction Models (`models/transaction.py`)

```python
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from enum import Enum

class TransactionType(str, Enum):
    PAYMENT = "payment"
    TRANSFER = "transfer"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    CRYPTO_ONRAMP = "crypto_onramp"
    CRYPTO_OFFRAMP = "crypto_offramp"
    P2P = "p2p"
    MERCHANT = "merchant"

class TransactionEvent(BaseModel):
    transaction_id: str
    timestamp: datetime
    amount: Decimal               # Always Decimal, never float (I-01)
    currency: str                 # ISO 4217
    sender_id: str
    receiver_id: str | None
    transaction_type: TransactionType
    sender_jurisdiction: str      # ISO 3166 alpha-2
    receiver_jurisdiction: str | None
    sender_risk_level: str = "standard"
    channel: str = "api"          # api, mobile, web
    metadata: dict = {}

class RiskScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)  # 0=safe, 1=critical
    factors: list[RiskFactor] = []
    model_version: str = "v1"
    computed_at: datetime

class RiskFactor(BaseModel):
    name: str                    # e.g. "velocity_24h"
    weight: float
    value: float
    explanation: str             # Human-readable
    regulation_ref: str | None   # e.g. "EBA GL 4.2.3"
```

## Phase 2 — Risk Scoring Pipeline

### 2.1 Risk Scorer (`scoring/risk_scorer.py`)

Pipeline steps:
1. Feature extraction (velocity, amount, jurisdiction, patterns)
2. Jube rules evaluation (via JubeAdapter, existing)
3. ML model scoring (scikit-learn IsolationForest, local)
4. Score aggregation (weighted: rules 40%, ML 30%, velocity 30%)
5. Threshold classification (low <0.3, medium 0.3-0.6, high 0.6-0.8, critical >0.8)

### 2.2 Feature Extractor (`scoring/feature_extractor.py`)

Features:
- `velocity_1h`: transaction count in last 1 hour
- `velocity_24h`: transaction count in last 24 hours
- `amount_deviation`: deviation from customer average
- `jurisdiction_risk`: FATF greylist check (I-03)
- `new_counterparty`: first-time receiver flag
- `round_amount`: round number detection (structuring)
- `time_anomaly`: unusual hour for customer profile
- `crypto_flag`: crypto on/off ramp flag
- `cross_border`: sender != receiver jurisdiction
- `pep_proximity`: connection to PEP

### 2.3 Velocity Tracker (`scoring/velocity_tracker.py`)

- Redis-based sliding window counters (existing Redis :6379)
- Keys: `velocity:{customer_id}:{window}` (1h, 24h, 7d)
- Configurable thresholds per customer risk level
- EDD trigger at GBP 10,000 cumulative (I-04)
- Hard-block jurisdictions: RU/BY/IR/KP/CU/MM/AF/VE (I-02)

### 2.4 ML Model (`scoring/ml_model.py`)

- Algorithm: IsolationForest (scikit-learn, free/OSS)
- Training: offline on historical transaction data
- Features: 10 features from feature_extractor
- Model storage: `models/isolation_forest_v1.joblib`
- Retraining: scheduled monthly via experiment copilot
- Explainability: SHAP values for each prediction

## Phase 3 — Explainable Alert System

### 3.1 Alert Generator (`alerts/alert_generator.py`)

For each transaction with risk_score > threshold:
1. Create AMLAlert with risk factors breakdown
2. Query Compliance KB for relevant regulation
3. Generate human-readable explanation
4. Attach regulation citations
5. Route to appropriate reviewer

### 3.2 Alert Model (`models/alert.py`)

```python
class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AMLAlert(BaseModel):
    alert_id: str
    transaction_id: str
    customer_id: str
    severity: AlertSeverity
    risk_score: RiskScore
    explanation: str             # Human-readable summary
    regulation_refs: list[str]   # KB citation IDs
    recommended_action: str      # "review", "escalate", "auto-close"
    created_at: datetime
    assigned_to: str | None = None
    marble_case_id: str | None = None
    status: str = "open"         # open, reviewing, escalated, closed
    review_deadline: datetime | None = None  # 24h SLA
```

### 3.3 Explanation Engine (`alerts/explanation_engine.py`)

Generates audit-trail explanations:
```
ALERT: High-risk transaction detected
Transaction: TXN-2026-04-11-0042
Amount: GBP 15,200.00 (3.2x customer average)
Risk Score: 0.82 (CRITICAL)

Risk Factors:
  1. Velocity (24h): 12 txns in 24h (threshold: 8) [weight: 0.30]
     -> EBA GL 4.2.3: ongoing monitoring frequency
  2. Cross-border: UK -> AE (high-risk corridor) [weight: 0.25]
     -> FATF Rec 16: wire transfer rules
  3. Round amount: GBP 15,200.00 (structuring pattern) [weight: 0.20]
     -> MLR 2017 Reg.33: suspicious patterns
  4. New counterparty: first-time receiver [weight: 0.15]

Recommended: ESCALATE to MLRO
Review deadline: 2026-04-12 21:00 UTC (24h SLA)
```

### 3.4 Alert Router (`alerts/alert_router.py`)

Routing rules:
- CRITICAL (>0.8): Marble case + immediate MLRO notification
- HIGH (0.6-0.8): Marble case + analyst queue
- MEDIUM (0.3-0.6): Auto-enrichment + analyst review within 48h
- LOW (<0.3): Auto-close with audit log

Integrations:
- Marble adapter: create case via MarbleAdapter (existing)
- Jube adapter: enrich with fraud rules (existing)
- KB query: attach regulation citations from Part 1

## Phase 4 — MCP Tools (5 new tools)

Add to `banxe_mcp/tools/transaction_monitor.py`:

Tool 1: `monitor.score_transaction`
- Score a single transaction event
- Input: TransactionEvent
- Output: RiskScore + factors + explanation

Tool 2: `monitor.get_alerts`
- List alerts by severity, status, customer, date range
- Output: paginated AMLAlert list

Tool 3: `monitor.get_alert_detail`
- Full alert with explanation + KB citations
- Input: alert_id
- Output: AMLAlert + full explanation

Tool 4: `monitor.get_velocity`
- Get velocity metrics for a customer
- Input: customer_id, windows (1h, 24h, 7d)
- Output: velocity counts + threshold status

Tool 5: `monitor.dashboard_metrics`
- Aggregate monitoring metrics for dashboard
- Output: alert counts by severity, avg review time, SAR yield

## Phase 5 — FastAPI Endpoints

```
POST /api/v1/monitor/score           # Score transaction
GET  /api/v1/monitor/alerts           # List alerts
GET  /api/v1/monitor/alerts/{id}      # Alert detail + explanation
PATCH /api/v1/monitor/alerts/{id}     # Update status (review/close)
GET  /api/v1/monitor/velocity/{cid}   # Customer velocity
GET  /api/v1/monitor/metrics           # Dashboard metrics
POST /api/v1/monitor/backtest          # Backtest rules on historical
GET  /api/v1/monitor/health            # Health check
```

## Phase 6 — Tests (50+ tests)

```
tests/test_transaction_monitor/
  test_transaction_models.py       # 6 tests
  test_event_consumer.py           # 5 tests (mocked RabbitMQ)
  test_feature_extractor.py        # 8 tests
  test_risk_scorer.py              # 7 tests
  test_velocity_tracker.py         # 6 tests (mocked Redis)
  test_alert_generator.py          # 5 tests
  test_explanation_engine.py        # 5 tests
  test_alert_router.py             # 4 tests
  test_mcp_tools.py                # 5 tests
  test_api_routes.py               # 6 tests
```

### Key test scenarios:
- Transaction with amount > 3x average scores HIGH
- Hard-block jurisdiction (RU) returns CRITICAL immediately
- Velocity > threshold triggers EDD (I-04)
- Explanation includes regulation refs from KB
- CRITICAL alert creates Marble case
- LOW alert auto-closes with audit log
- Round amount detection flags structuring
- Cross-border high-risk corridor scores correctly
- Dashboard metrics aggregate correctly
- Backtest returns hit rate improvement

## Phase 7 — Infrastructure

### Docker service (`docker/docker-compose.transaction-monitor.yaml`)

```yaml
services:
  transaction-monitor:
    build: ./services/transaction_monitor
    ports:
      - "8099:8099"
    environment:
      - REDIS_URL=redis://redis:6379
      - JUBE_URL=http://jube:5001
      - MARBLE_URL=http://marble:5002
      - CLICKHOUSE_URL=http://clickhouse:8123
      - KB_MCP_URL=http://compliance-kb:8098
      - ML_MODEL_PATH=/app/models/isolation_forest_v1.joblib
    depends_on:
      - redis
      - compliance-kb
```

### Requirements (all free/OSS)

```
scikit-learn>=1.4.0
shap>=0.44.0
aio-pika>=9.4.0        # RabbitMQ async
redis>=5.0.0
httpx>=0.26.0
fastapi>=0.109.0
pydantic>=2.5.0
joblib>=1.3.0
```

## Acceptance Criteria

- [ ] Event consumer processes RabbitMQ/Redis stream
- [ ] Risk scorer combines rules (40%) + ML (30%) + velocity (30%)
- [ ] 10 ML features extracted per transaction
- [ ] IsolationForest model trained on sample data
- [ ] Explainable alerts with regulation citations from KB
- [ ] Alert router: CRITICAL->Marble, LOW->auto-close
- [ ] Velocity tracker uses Redis sliding windows
- [ ] Hard-block jurisdictions enforced (I-02)
- [ ] EDD threshold at GBP 10k (I-04)
- [ ] 5 MCP tools registered
- [ ] 8 FastAPI endpoints operational
- [ ] 50+ tests passing
- [ ] Docker compose service runs with dependencies
- [ ] All dependencies free/OSS

## Execution Order

1. Create directory structure
2. Implement transaction + alert Pydantic models
3. Build feature extractor (10 features)
4. Implement velocity tracker (Redis)
5. Build risk scorer pipeline (rules + ML + velocity)
6. Train IsolationForest on sample data
7. Implement explanation engine with KB integration
8. Build alert generator + router
9. Register 5 MCP tools
10. Add FastAPI routes
11. Write tests
12. Docker compose

## Integration Summary (All 3 Parts)

```
Part 1 (Knowledge Service)  -->  Part 2 (Experiment Copilot)  -->  Part 3 (Transaction Monitor)
   |                                   |                                    |
   | kb.query()                         | experiment.design()                | monitor.score_transaction()
   | kb.search()                        | experiment.get_metrics()           | monitor.get_alerts()
   | kb.compare_versions()              | experiment.propose_change()        | monitor.dashboard_metrics()
   |                                   |                                    |
   +-- ChromaDB (vectors)              +-- YAML store (experiments)         +-- Redis (velocity)
   +-- 6 MCP tools                     +-- 4 MCP tools                     +-- 5 MCP tools
   +-- 8 API endpoints                 +-- 8 API endpoints                 +-- 8 API endpoints
   +-- 40+ tests                       +-- 45+ tests                       +-- 50+ tests

Total: 15 new MCP tools | 24 new API endpoints | 135+ new tests
```

---

*Ticket: IL-RTM-01 | Prompt: 17 Part 3/3*
*Complete Feature 17: Compliance AI Copilot + Knowledge Service + Transaction Monitor*
