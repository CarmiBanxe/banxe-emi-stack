# ARCHITECTURE — Agent Routing Layer (ARL)

## Overview

The Agent Routing Layer is a cost-optimization and quality-improvement system
that routes LLM tasks across three tiers based on complexity, risk, and cached
reasoning patterns. Inspired by Ruflo's token-routing approach, adapted for
regulated banking compliance.

## Problem Statement

Current architecture sends ALL compliance/AML/KYC tasks to a single top-tier
LLM model. ~70-80% of these tasks are routine (sanctions list lookup, simple
limit checks, known-pattern transactions) and do not require expensive reasoning.

**Result:** Excessive token spend, slow processing, no cost visibility per task type.

## Solution: Three-Tier Routing + ReasoningBank + Swarm

### Core Components

```
Events (Kafka/RabbitMQ)
    |
    v
[Agent Gateway] --> [ReasoningBank] (similarity search)
    |                     |
    |--- Tier1Queue ----> [Tier1Worker] (rules, BM25, cheap LLM)
    |--- Tier2Queue ----> [Tier2Worker] (mid-tier LLM)
    |--- Tier3Queue ----> [Tier3Worker] (top model / Swarm)
    |--- SwarmQueue ----> [SwarmOrchestrator]
    |                          |
    v                     [AgentRegistry]
[Telemetry + PolicyEngine]     |
    |                     Specialized Agents:
    v                     - SanctionsAgent
[Grafana Dashboards]      - BehaviorAgent
                          - GeoRiskAgent
                          - ProfileHistoryAgent
                          - ProductLimitsAgent
```

### 1. Agent Gateway

Entry point for all LLM-requiring events. Responsibilities:
- Normalize domain events into `AgentTask` format
- Consult playbook (product + jurisdiction) for tier assignment
- Query ReasoningBank for similar cases before routing
- Write tasks to tier-specific queues
- Publish results back to event bus

### 2. Tier System

| Tier | Model/Engine | Use Cases | Cost |
|------|-------------|-----------|------|
| Tier 1 | Rule engine / BM25 / cheap LLM | Sanctions list check, limit validation, known-pattern match | ~$0 |
| Tier 2 | Mid-tier LLM (Haiku-class) | New beneficiary analysis, payment description NLP, support responses | Low |
| Tier 3 | Top model (Opus-class) / Swarm | Complex investigations, conflicting signals, cross-border high-risk | High |

### 3. ReasoningBank

Vector store + structured case memory for compliance decisions.

**Entities:**
- `case_record` — canonical case snapshot
- `decision_record` — final decision + status
- `reasoning_record` — structured reasoning chain (3 views: internal, audit, customer)
- `embedding_record` — HNSW/FAISS vectors for similarity search
- `policy_snapshot` — which rules/playbook version applied
- `feedback_record` — late outcomes (false positive, SAR filed, dispute)

**Key API:**
- `POST /reasoning/store` — save case + decision + reasoning
- `POST /reasoning/similar` — find similar cases (top_k)
- `POST /reasoning/reuse` — get reusable reasoning snippets
- `GET /reasoning/{case_id}/explain/{view}` — get explanation (audit/customer/internal)

**Reuse Rules:**
- Same playbook family
- Compatible policy version
- Similarity above threshold
- No concept drift detected
- No human override that contradicted original decision

### 4. Swarm Orchestrator

For Tier 3 complex cases, launches multiple specialized agents.

**Topologies:**
| Scenario | Topology | Why |
|----------|----------|-----|
| AML triage | Star | Independent signals, fast aggregation |
| Enhanced investigation | Hierarchy | Coordinator + subordinate agents |
| KYC onboarding | Ring | Sequential: docs → profile → PEP/sanctions |
| Cross-border complex | Hierarchy+Star | Parallel checks + coordinator |

**Agent Contract (unified response):**
```json
{
  "agent_name": "sanctions_agent",
  "case_id": "case_123",
  "signal_type": "sanctions_screening",
  "risk_score": 0.15,
  "confidence": 0.95,
  "decision_hint": "clear",
  "reason_summary": "No matches in OFAC, EU, UN lists",
  "evidence_refs": ["ofac_check_id_456"],
  "token_cost": 0,
  "latency_ms": 45
}
```

**Aggregation Rules (deterministic first):**
- Any agent returns `block` with high confidence → minimum `hold`
- 3+ independent `warning` signals above threshold → `manual_review`
- All critical agents `clear` + risk below threshold → `approve`
- LLM aggregation only for Tier 3 conflicting cases

### 5. Playbook Engine

YAML-based routing rules per product/jurisdiction.

**Example: EU SEPA Retail**
```yaml
playbook_id: eu_sepa_retail_v1
product: sepa_retail_transfer
jurisdictions: [EU, EEA]

tiers:
  tier1:
    max_amount_eur: 1000
    allowed_if:
      - known_beneficiary = true
      - sanctions_hit = false
      - device_risk in [low]
      - anomaly_count <= 1
  tier2:
    triggers:
      - new_beneficiary = true
      - amount_spike = true
      - customer_age_days < 30
  tier3:
    triggers:
      - sanctions_hit = true
      - cumulative_risk_score >= 0.75
      - amount_eur > 10000

swarm:
  topology: star
  agents: [sanctions, behavior, geo_risk, profile_history]

decision:
  approve_if: all_critical_clean AND risk < 0.25
  manual_review_if: confidence < 0.7 OR conflicting_signals
  decline_if: policy_block = true
```

### 6. Telemetry & Policy Engine

**Required Metrics:**
- `tokens_input/output` per agent, tier, event type, jurisdiction, product
- `auto_approved / auto_declined / manual_review` ratios
- `human_override_rate` (disagreement with agent decision)
- `latency_p50/p95/p99` per tier
- `queue_depth` per tier
- `reasoning_reuse_rate` (cache hit ratio)
- `cost_per_decision` by product/jurisdiction

**Policy Controls:**
- Token budget limits per tier/agent/hour
- Auto-downgrade tier during budget pressure (low-risk only)
- Feature flags for swarm/background workers
- Fallback to rule-only mode on LLM failures

## Implementation Roadmap

| Phase | What | Value |
|-------|------|-------|
| Phase 1 | Playbook engine + Tier routing | Immediate token savings ~60-70% |
| Phase 2 | ReasoningBank (store + retrieve) | Reduce repeated reasoning, improve consistency |
| Phase 3 | Swarm Orchestrator | Better quality for complex AML/KYC cases |
| Phase 4 | Telemetry dashboards + Policy Engine | Cost visibility, budget control |
| Phase 5 | ML router (replace rule-based tier assignment) | Self-improving routing accuracy |

## FCA/EU Regulatory References

- EU AI Act Art.14 — Human oversight for high-risk AI decisions
- MLR 2017 Reg.26-28 — AML monitoring and screening
- GDPR Art.22 — Rights related to automated decision-making
- PSD2 SCA — Transaction authentication requirements

## Files

- `services/agent_routing/` — Agent Gateway, Tier Workers
- `services/reasoning_bank/` — ReasoningBank service
- `services/swarm/` — Swarm Orchestrator
- `config/playbooks/` — YAML playbook files
- `infra/grafana/dashboards/agent-routing-metrics.json` — Monitoring

---

*Created: 2026-04-11 | Ticket: IL-ARL-01*
