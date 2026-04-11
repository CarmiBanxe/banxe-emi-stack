# Prompt 14 — Agent Routing Layer (ARL)

> Ticket: IL-ARL-01 | Branch: refactor/claude-ai-scaffold
> Architecture: docs/ARCHITECTURE-AGENT-ROUTING.md
> Date: 2026-04-11

## Goal

Implement a three-tier Agent Routing Layer that optimizes LLM token spend
by routing compliance/AML/KYC tasks based on complexity, risk level,
and cached reasoning patterns. Target: ~60-70% token cost reduction
for routine operations.

## Reference

Read `docs/ARCHITECTURE-AGENT-ROUTING.md` before starting.
Follow existing project patterns from `services/`, `config/`, `tests/`.

## Phase 1 — Data Models & Schemas

Create `services/agent_routing/models.py`:

```python
# AgentTask — normalized task envelope
@dataclass
class AgentTask:
    task_id: str          # UUID
    event_type: str       # e.g. "aml_screening", "kyc_check", "payment_review"
    tier: int             # 1, 2, or 3 (assigned by gateway)
    payload: dict         # domain-specific data
    product: str          # e.g. "sepa_retail_transfer"
    jurisdiction: str     # e.g. "EU", "UK"
    customer_id: str
    risk_context: dict    # pre-computed risk signals
    created_at: datetime
    playbook_id: str      # which playbook matched
    reasoning_hint: Optional[dict]  # from ReasoningBank if found
```

Create `services/agent_routing/schemas.py`:

```python
# AgentResponse — unified response from any tier/agent
@dataclass
class AgentResponse:
    agent_name: str
    case_id: str
    signal_type: str
    risk_score: float        # 0.0 - 1.0
    confidence: float        # 0.0 - 1.0
    decision_hint: str       # "clear", "warning", "block", "manual_review"
    reason_summary: str
    evidence_refs: list[str]
    token_cost: int
    latency_ms: int

# TierResult — final routing decision
@dataclass
class TierResult:
    task_id: str
    tier_used: int
    decision: str            # "approve", "decline", "manual_review", "hold"
    responses: list[AgentResponse]
    total_tokens: int
    total_latency_ms: int
    reasoning_reused: bool
    playbook_version: str
```

## Phase 2 — Playbook Engine

Create `services/agent_routing/playbook_engine.py`:
- Load YAML playbooks from `config/playbooks/`
- Match incoming event to playbook by (product, jurisdiction)
- Evaluate tier assignment rules against risk_context
- Return: assigned tier + matched playbook_id

Create `config/playbooks/eu_sepa_retail_v1.yaml`:
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

Create `config/playbooks/uk_fps_retail_v1.yaml` (similar structure for UK FPS).
Create `config/playbooks/high_risk_jurisdiction_v1.yaml` (always tier3).

## Phase 3 — Agent Gateway

Create `services/agent_routing/gateway.py`:
- `AgentGateway` class — entry point for all LLM-requiring events
- normalize_event(domain_event) -> AgentTask
- assign_tier(task, playbook) -> int
- query ReasoningBank for similar cases (if available)
- route to tier-specific queue (RabbitMQ)
- publish results back to event bus
- Metrics: emit tokens_input/output, latency, tier assignment

Create `services/agent_routing/tier_workers.py`:
- `Tier1Worker`: rule engine + BM25 + optional cheap LLM
  - Sanctions list check (local OFAC/EU/UN lists)
  - Limit validation (amount thresholds)
  - Known-pattern matching
  - Cost: ~$0 per decision
- `Tier2Worker`: mid-tier LLM (Haiku-class via Ollama or API)
  - New beneficiary analysis
  - Payment description NLP
  - Behavioral anomaly assessment
- `Tier3Worker`: top model (Opus-class) or delegates to SwarmOrchestrator
  - Complex investigations
  - Conflicting signals resolution
  - Cross-border high-risk analysis

## Phase 4 — ReasoningBank

Create `services/reasoning_bank/` package:

`services/reasoning_bank/models.py`:
- CaseRecord, DecisionRecord, ReasoningRecord
- EmbeddingRecord, PolicySnapshot, FeedbackRecord

`services/reasoning_bank/store.py`:
- PostgreSQL storage for structured records
- FAISS/HNSW index for embedding similarity search
- store_case(case, decision, reasoning) -> case_id
- find_similar(embedding, top_k=5, threshold=0.85) -> list[CaseRecord]
- get_reusable_reasoning(case_id) -> Optional[ReasoningRecord]

`services/reasoning_bank/api.py` (FastAPI router):
- POST /reasoning/store
- POST /reasoning/similar
- POST /reasoning/reuse
- GET /reasoning/{case_id}/explain/{view}  (view: audit|customer|internal)

Reuse rules:
- Same playbook family
- Compatible policy version
- Similarity above threshold (configurable, default 0.85)
- No concept drift detected
- No human override that contradicted original decision

## Phase 5 — Swarm Orchestrator

Create `services/swarm/orchestrator.py`:
- `SwarmOrchestrator` class
- launch_swarm(task, topology, agent_names) -> TierResult
- Topologies:
  - Star: independent parallel agents, aggregate results
  - Hierarchy: coordinator + subordinate agents
  - Ring: sequential pipeline (e.g. docs -> profile -> PEP)
- Agent registry: load from config/agents/

Create `services/swarm/agents/` directory with:
- `sanctions_agent.py` — OFAC/EU/UN screening
- `behavior_agent.py` — transaction pattern analysis
- `geo_risk_agent.py` — jurisdiction risk assessment
- `profile_history_agent.py` — customer history analysis
- `product_limits_agent.py` — product-specific limit checks

Each agent implements `BaseAgent` interface:
```python
class BaseAgent(ABC):
    @abstractmethod
    async def analyze(self, task: AgentTask) -> AgentResponse: ...
    @property
    def agent_name(self) -> str: ...
    @property
    def signal_type(self) -> str: ...
```

Aggregation rules (deterministic first, LLM only for conflicts):
- Any agent returns `block` + high confidence -> minimum `hold`
- 3+ independent `warning` signals above threshold -> `manual_review`
- All critical agents `clear` + risk < threshold -> `approve`
- Conflicting signals -> Tier 3 LLM aggregation

## Phase 6 — Telemetry & Policy Engine

Create `services/agent_routing/telemetry.py`:
- Emit metrics to ClickHouse:
  - tokens_input/output per agent, tier, event_type, jurisdiction, product
  - auto_approved / auto_declined / manual_review ratios
  - human_override_rate
  - latency_p50/p95/p99 per tier
  - queue_depth per tier
  - reasoning_reuse_rate (cache hit ratio)
  - cost_per_decision by product/jurisdiction

Create `services/agent_routing/policy_engine.py`:
- Token budget limits per tier/agent/hour
- Auto-downgrade tier during budget pressure (low-risk only)
- Feature flags for swarm/background workers
- Fallback to rule-only mode on LLM failures

Create `infra/grafana/dashboards/agent-routing-metrics.json`:
- Dashboard with panels for all metrics above
- Alert rules for budget overrun and latency spikes

## Phase 7 — Tests

Create `tests/test_agent_routing/`:
- `test_playbook_engine.py` — playbook loading, tier assignment logic
- `test_gateway.py` — event normalization, routing decisions
- `test_tier_workers.py` — each tier worker processes tasks correctly
- `test_reasoning_bank.py` — store/retrieve/similarity/reuse
- `test_swarm_orchestrator.py` — star/hierarchy/ring topologies
- `test_agents.py` — each specialized agent returns valid AgentResponse
- `test_telemetry.py` — metrics emission
- `test_policy_engine.py` — budget limits, auto-downgrade, fallback

Minimum 120 tests. All must pass. Coverage >= 80%.

## Phase 8 — MCP Tools Integration

Add to `banxe_mcp/tools/`:
- `route_agent_task` — submit task to Agent Gateway
- `query_reasoning_bank` — find similar cases
- `get_routing_metrics` — current telemetry snapshot
- `manage_playbooks` — list/validate playbooks

Register in `.ai/registries/mcp-tools.yaml`.

## Phase 9 — Integration

- Wire AgentGateway into existing AML/KYC pipeline
- Add feature flag `AGENT_ROUTING_ENABLED` (default: false)
- When enabled, route through ARL instead of direct LLM calls
- Ensure HITL feedback loop (IL-056) feeds back into ReasoningBank
- Update `docker/docker-compose.yml` with reasoning_bank service

## Regulatory Compliance

- EU AI Act Art.14: Human oversight for Tier 3 decisions
- MLR 2017 Reg.26-28: AML monitoring audit trail
- GDPR Art.22: Explainability for automated decisions (3 views)
- PSD2 SCA: Transaction auth requirements preserved

## Files Checklist

```
services/agent_routing/__init__.py
services/agent_routing/models.py
services/agent_routing/schemas.py
services/agent_routing/gateway.py
services/agent_routing/tier_workers.py
services/agent_routing/playbook_engine.py
services/agent_routing/telemetry.py
services/agent_routing/policy_engine.py
services/reasoning_bank/__init__.py
services/reasoning_bank/models.py
services/reasoning_bank/store.py
services/reasoning_bank/api.py
services/swarm/__init__.py
services/swarm/orchestrator.py
services/swarm/agents/__init__.py
services/swarm/agents/base_agent.py
services/swarm/agents/sanctions_agent.py
services/swarm/agents/behavior_agent.py
services/swarm/agents/geo_risk_agent.py
services/swarm/agents/profile_history_agent.py
services/swarm/agents/product_limits_agent.py
config/playbooks/eu_sepa_retail_v1.yaml
config/playbooks/uk_fps_retail_v1.yaml
config/playbooks/high_risk_jurisdiction_v1.yaml
infra/grafana/dashboards/agent-routing-metrics.json
tests/test_agent_routing/  (8+ test files, 120+ tests)
```

## Infrastructure Utilization Canon

- [x] PostgreSQL: ReasoningBank structured storage
- [x] ClickHouse: telemetry metrics
- [x] RabbitMQ: tier queues
- [x] Redis: velocity/cache layer
- [x] Grafana: agent-routing dashboard
- [x] FastAPI: ReasoningBank API endpoints
- [x] MCP: 4 new tools registered
- [x] Docker: reasoning_bank service added
- [x] YAML config: playbooks
- [x] Semgrep: rules for agent routing patterns

## Verification

1. `ruff check .` — zero warnings
2. `pytest tests/test_agent_routing/ -v` — 120+ tests green
3. `coverage report` — >= 80%
4. Playbook YAML validates against schema
5. All MCP tools callable via banxe_mcp
6. Grafana dashboard JSON valid
7. Feature flag toggles routing on/off cleanly

---
*Created: 2026-04-11 | Ticket: IL-ARL-01 | Prompt: 14*
