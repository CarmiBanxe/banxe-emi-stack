# ARCHITECTURE-17: Compliance AI Copilot

> BANXE EMI Stack | Feature 17 | Agentic AML/KYC Compliance Platform

## Overview

Full-stack compliance AI system with 3 integrated services:
1. **Knowledge Service** - RAG-based compliance KB (ChromaDB + MCP)
2. **Experiment Copilot** - AML rule experimentation + Git-based workflow
3. **Transaction Monitor** - Realtime scoring + explainable alerts

## System Architecture

```
                    +---------------------------+
                    |     Compliance AI Copilot  |
                    +---------------------------+
                    |                           |
        +-----------+-----------+   +-----------+-----------+
        |   Knowledge Service   |   | Experiment Copilot    |
        |   (ChromaDB + MCP)    |   | (YAML + Git + Claude) |
        |   Port: 8098          |   | Port: 8100            |
        +-----------+-----------+   +-----------+-----------+
                    |                           |
        +-----------+-----------+---------------+
        |                       |
        |   Transaction Monitor |
        |   (ML + Rules + Redis)|
        |   Port: 8099          |
        +-----------+-----------+
                    |
    +---------------+---------------+
    |               |               |
+---+---+     +-----+-----+   +----+----+
| Jube  |     |  Marble   |   | Redis   |
| :5001 |     |  :5002    |   | :6379   |
+-------+     +-----------+   +---------+
```

## Services

### Part 1: Knowledge Service (Port 8098)
| Component | Technology | Cost |
|-----------|-----------|------|
| Vector Store | ChromaDB | Free/OSS |
| Embeddings | sentence-transformers (MiniLM) | Free/OSS |
| PDF Parser | PyMuPDF + unstructured | Free/OSS |
| API | FastAPI | Free/OSS |
| MCP Tools | 6 tools (query, search, compare) | - |

Notebooks: EU-AML, UK-FCA, Internal-SOP, Case-History

### Part 2: Experiment Copilot (Port 8100)
| Component | Technology | Cost |
|-----------|-----------|------|
| Store | YAML files in Git | Free |
| Agents | 4 (designer, proposer, steward, reporter) | - |
| Metrics | ClickHouse queries | Free/OSS |
| PRs | GitHub REST API | Free |
| MCP Tools | 4 tools (design, list, metrics, propose) | - |

Targets: hit-rate 6%->65%, FP 94%->35%, SAR yield 6.5%->20%

### Part 3: Transaction Monitor (Port 8099)
| Component | Technology | Cost |
|-----------|-----------|------|
| ML Model | scikit-learn IsolationForest | Free/OSS |
| Explainability | SHAP | Free/OSS |
| Stream | RabbitMQ (aio-pika) | Free/OSS |
| Velocity | Redis sliding windows | Free/OSS |
| MCP Tools | 5 tools (score, alerts, velocity, metrics) | - |

Scoring: Rules 40% + ML 30% + Velocity 30%

## MCP Tools Summary (15 new)

| Service | Tools | Purpose |
|---------|-------|---------|
| KB | kb.query, kb.search, kb.list_notebooks, kb.get_notebook, kb.compare_versions, kb.get_citations | Knowledge retrieval |
| Experiment | experiment.design, experiment.list, experiment.get_metrics, experiment.propose_change | AML experiments |
| Monitor | monitor.score_transaction, monitor.get_alerts, monitor.get_alert_detail, monitor.get_velocity, monitor.dashboard_metrics | Realtime monitoring |

## API Endpoints (24 new)

- Knowledge Service: 8 endpoints (/api/v1/kb/*)
- Experiment Copilot: 8 endpoints (/api/v1/experiments/*)
- Transaction Monitor: 8 endpoints (/api/v1/monitor/*)

## Invariants Enforced

- I-01: No float for money (Decimal strings)
- I-02: Hard-block jurisdictions (RU/BY/IR/KP/CU/MM/AF/VE)
- I-03: FATF greylist -> EDD (23 countries)
- I-04: EDD threshold GBP 10k
- I-27: HITL feedback supervised (PROPOSES only)

## Test Coverage: 135+ new tests

| Suite | Tests |
|-------|-------|
| Knowledge Service | 40+ |
| Experiment Copilot | 45+ |
| Transaction Monitor | 50+ |

---

*Ticket: IL-CKS-01, IL-CEC-01, IL-RTM-01 | Prompt: 17 (3 parts)*
