# B-8 Anti-Fraud Observability & Guardrails — Implementation Blueprint
<!-- Sprint: B-8 | Branch: agent/factory/bankingengine/b8-observability | Status: BLUEPRINT -->
<!-- I-27: AI proposes — human decides. SANDBOX ONLY. No runtime code modified in this document. -->

## 0. Invariants & Constraints (always in effect)

| ID | Rule |
|----|------|
| I-01 | `Decimal` for all GBP amounts; non-monetary scores use `float` with `# nosemgrep` annotation |
| I-02 | Hard-block jurisdictions RU/BY/IR/KP/CU/MM/AF/VE/SY — enforced in FraudAMLPipeline already |
| I-06 | Sanctions HARD_BLOCK — already in decision matrix; guardrails MUST NOT soften it |
| I-24 | Append-only audit logs — new events are **added**, never mutated or deleted |
| I-27 | AI proposes; human decides. Every new alert type requires HITL L4 acknowledge gate |
| I-71 | No push/merge from factory agent — operator executes merge |
| SANDBOX | All thresholds marked **[PLACEHOLDER]** below require MLRO/CRO sign-off before production |

---

## 1. Sprint Scope

**Sprint B-8 adds** to the existing decision spine without replacing it:

1. **Structured reason codes** — replace free-text `list[str]` in `PipelineResult` with typed `ReasonCode` objects that carry policy-trace metadata alongside the existing human-readable string.
2. **Pipeline observability events** — emit a single structured `FraudAMLEvent` per `assess()` call, consumable by `ObservabilityAgent`, metrics scrapers, and audit trail.
3. **New alert types** — extend `ObservabilityAgent._generate_alerts()` with `FRAUD_SCORING`, `MODEL_FALLBACK`, `GUARDRAIL_HIT`, and `HITL_ESCALATION` alert types.
4. **Model governance hook** — instrument `IsolationForestModel._load()` to emit a `MODEL_FALLBACK` event when the primary model is absent; add a `ModelVersionInfo` dataclass for future drift tracking.
5. **Guardrail rules** — define a `GuardrailPolicy` interface and three concrete guardrail checks (`LatencyGuardrail`, `ScoreAnomalyGuardrail`, `FallbackGuardrail`) callable from the pipeline without altering the decision matrix.
6. **Feature flags** — introduce a `FraudObservabilityConfig` settings object so every new hook can be disabled independently.

### Non-Goals (B-8 does NOT)

- Modify `PipelineDecision` values (`APPROVE`/`HOLD`/`BLOCK`) — these remain unchanged.
- Change the decision matrix priority (BLOCK > HOLD > APPROVE) at `fraud_aml_pipeline.py:254–260`.
- Write data to ClickHouse directly (caller / audit trail service remains responsible per existing design).
- Load LightGBM or any new ML library.
- Add production connectors to Sardine, Marble, or Jube.
- Replace `ExplanationEngine` (`services/transaction_monitor/alerts/explanation_engine.py`) — it already exists for AML alerts and must not be rebuilt.
- Change `FraudScoringPort` Protocol interface (`services/fraud/fraud_port.py:95–102`).

---

## 2. Extension Points in Existing Code

### 2.1 `PipelineResult.block_reasons` / `.hold_reasons`

**File:** `services/fraud/fraud_aml_pipeline.py`  
**Lines:** 135–136 (field declarations), 220–252 (population)

Current type: `list[str]` — plain human-readable strings assembled inside `assess()`.

**Minimal-diff change:** Introduce a `ReasonCode` dataclass in a new file `services/fraud/reason_codes.py`. Keep `list[str]` fields on `PipelineResult` for backward compatibility; add parallel `block_reason_codes: list[ReasonCode]` and `hold_reason_codes: list[ReasonCode]` fields with `field(default_factory=list)` so existing callers are unaffected.

Population: at each decision branch in `assess()` (lines 224–252) call `ReasonCode.from_fraud(...)` / `ReasonCode.from_aml(...)` and append to the new lists alongside the existing string append.

### 2.2 `FraudScoringResult.factors`

**File:** `services/fraud/fraud_port.py`  
**Line:** 89 — `factors: list[str] = field(default_factory=list)`

`factors` carries human-readable fraud scoring reasons from the provider adapter. The Protocol interface must remain unchanged.

**Extension:** `ReasonCode.from_fraud_factors(factors: list[str], provider: str, score: int) → list[ReasonCode]` — wraps existing strings into `ReasonCode` without touching the Protocol.

### 2.3 `FraudAMLPipeline.assess()` — post-decision hook point

**File:** `services/fraud/fraud_aml_pipeline.py`  
**Line:** 262 — `total_ms = (time.monotonic() - t0) * 1000`  
**Line:** 263 — `logger.info(...)` — current logging call

**Extension:** immediately after `total_ms` (line 262) and before the `logger.info` call, call an injected optional `ObservabilityPort.emit(FraudAMLEvent)`. The port defaults to `NoopObservabilityPort` (no-op) so the pipeline remains testable without an observability dependency.

Constructor change (additive only):
```python
def __init__(
    self,
    fraud_adapter: FraudScoringPort,
    tx_monitor: TxMonitorService,
    observability: ObservabilityPort | None = None,   # NEW — optional
) -> None:
    ...
    self._obs = observability or NoopObservabilityPort()
```

### 2.4 `ObservabilityAgent._generate_alerts()`

**File:** `services/observability/observability_agent.py`  
**Lines:** 83–113

Current alert types: `HEALTH`, `COMPLIANCE`. Both use `hashlib.sha256` for deterministic alert IDs.

**Extension:** Add a `register_fraud_event(event: FraudAMLEvent) → None` method on `ObservabilityAgent`. When called, it calls `_generate_fraud_alerts(event)` (new private method) and appends to `self._alerts` (I-24 append-only, line 64).

The `snapshot()` method (line 66) remains unchanged — it does not poll fraud events; fraud alerts are pushed by the pipeline post-decision hook.

### 2.5 `IsolationForestModel._load()`

**File:** `services/transaction_monitor/scoring/risk_scorer.py`  
**Lines:** 67–75

Current fallback: `logger.warning("ML model not found at %s — using fallback", self._model_path)` at line 74.

**Extension:** After the warning, call an injected optional `ModelEventPort.on_fallback(model_path: str) → None`. Defaults to `NoopModelEventPort`. This is the `MODEL_FALLBACK` hook without changing `IsolationForestModel`'s scoring logic.

### 2.6 `MLModelPort` Protocol (model-adapter interface)

**File:** `services/transaction_monitor/scoring/risk_scorer.py`  
**Lines:** 37–41

```python
@runtime_checkable
class MLModelPort(Protocol):
    def score(self, features: dict[str, float]) -> float: ...
```

This Protocol already exists and is the correct future model-adapter interface. B-8 adds `ModelVersionInfo` alongside it (in the same file):

```python
@dataclass(frozen=True)
class ModelVersionInfo:
    name: str           # "IsolationForest v1", "LightGBM v1", etc.
    version: str        # semver or git SHA
    trained_at: str     # ISO-8601 UTC — for drift detection window
    features: list[str] # ordered feature list (for schema drift detection)
```

`IsolationForestModel` gains a `version_info: ModelVersionInfo` property (hardcoded for v1). A future LightGBM adapter simply implements `MLModelPort` and exposes its own `version_info`.

---

## 3. New Files

| Path | Purpose |
|------|---------|
| `services/fraud/reason_codes.py` | `ReasonCode` dataclass + factory methods |
| `services/fraud/fraud_aml_event.py` | `FraudAMLEvent` structured event dataclass |
| `services/fraud/observability_port.py` | `ObservabilityPort` Protocol + `NoopObservabilityPort` |
| `services/fraud/guardrails.py` | `GuardrailPolicy` Protocol + 3 concrete guardrails |
| `services/fraud/fraud_observability_config.py` | `FraudObservabilityConfig` feature flags |
| `services/transaction_monitor/scoring/model_event_port.py` | `ModelEventPort` Protocol + `NoopModelEventPort` + `ModelVersionInfo` |
| `tests/fraud/test_reason_codes.py` | ≥15 tests for ReasonCode factory methods |
| `tests/fraud/test_fraud_aml_event.py` | ≥15 tests for FraudAMLEvent schema |
| `tests/fraud/test_guardrails.py` | ≥15 tests for guardrail rules |
| `tests/observability/test_fraud_alerts.py` | ≥10 tests for new ObservabilityAgent alert types |

---

## 4. Data Schemas

### 4.1 `ReasonCode`

```python
# services/fraud/reason_codes.py

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ReasonDomain(str, Enum):
    FRAUD = "FRAUD"
    AML = "AML"
    GUARDRAIL = "GUARDRAIL"


class PolicyRef(str, Enum):
    """Regulatory / invariant references attached to each reason code."""
    PSR_APP_2024 = "PSR APP 2024"
    POCA_2002_S330 = "POCA 2002 s.330"
    MLR_2017_REG28 = "MLR 2017 Reg.28"
    BANXE_I02 = "Banxe I-02"
    BANXE_I04 = "Banxe I-04"
    BANXE_I06 = "Banxe I-06"
    GUARDRAIL_LATENCY = "Guardrail:LatencySLA"
    GUARDRAIL_SCORE_ANOMALY = "Guardrail:ScoreAnomaly"
    GUARDRAIL_FALLBACK = "Guardrail:MLFallback"


@dataclass(frozen=True)
class ReasonCode:
    code: str           # machine-readable, stable (e.g. "FRAUD_CRITICAL_SCORE")
    domain: ReasonDomain
    policy_ref: PolicyRef
    human_text: str     # the existing string from block_reasons / hold_reasons
    score_contribution: int | None = None  # fraud score 0-100 if applicable

    @classmethod
    def from_fraud_block(cls, score: int, factors: list[str]) -> "ReasonCode":
        return cls(
            code="FRAUD_CRITICAL_SCORE",
            domain=ReasonDomain.FRAUD,
            policy_ref=PolicyRef.PSR_APP_2024,
            human_text=f"Fraud CRITICAL (score={score}): " + "; ".join(factors),
            score_contribution=score,
        )

    @classmethod
    def from_sanctions_block(cls, reasons: list[str]) -> "ReasonCode":
        return cls(
            code="AML_SANCTIONS_HARD_BLOCK",
            domain=ReasonDomain.AML,
            policy_ref=PolicyRef.BANXE_I06,
            human_text="Sanctions hard block (I-06): " + "; ".join(reasons),
        )

    @classmethod
    def from_app_scam(cls, indicator: str) -> "ReasonCode":
        return cls(
            code=f"FRAUD_APP_SCAM_{indicator}",
            domain=ReasonDomain.FRAUD,
            policy_ref=PolicyRef.PSR_APP_2024,
            human_text=f"APP scam signal (PSR APP 2024): {indicator}",
        )

    @classmethod
    def from_edd_hold(cls) -> "ReasonCode":
        return cls(
            code="AML_EDD_REQUIRED",
            domain=ReasonDomain.AML,
            policy_ref=PolicyRef.MLR_2017_REG28,
            human_text="EDD required (MLR 2017 Reg.28)",
        )

    @classmethod
    def from_sar_hold(cls) -> "ReasonCode":
        return cls(
            code="AML_SAR_REQUIRED",
            domain=ReasonDomain.AML,
            policy_ref=PolicyRef.POCA_2002_S330,
            human_text="SAR consideration required (MLRO review)",
        )

    @classmethod
    def from_velocity_daily(cls) -> "ReasonCode":
        return cls(
            code="AML_VELOCITY_DAILY_BREACH",
            domain=ReasonDomain.AML,
            policy_ref=PolicyRef.BANXE_I04,
            human_text="Daily velocity threshold breached",
        )

    @classmethod
    def from_velocity_monthly(cls) -> "ReasonCode":
        return cls(
            code="AML_VELOCITY_MONTHLY_BREACH",
            domain=ReasonDomain.AML,
            policy_ref=PolicyRef.BANXE_I04,
            human_text="Monthly velocity threshold breached",
        )

    @classmethod
    def from_structuring(cls) -> "ReasonCode":
        return cls(
            code="AML_STRUCTURING_SIGNAL",
            domain=ReasonDomain.AML,
            policy_ref=PolicyRef.POCA_2002_S330,
            human_text="Structuring signal detected (POCA 2002 s.330)",
        )
```

### 4.2 `FraudAMLEvent`

```python
# services/fraud/fraud_aml_event.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from services.fraud.reason_codes import ReasonCode


class ModelProvenance(str, Enum):
    PRIMARY = "PRIMARY"    # IsolationForest or production model loaded successfully
    FALLBACK = "FALLBACK"  # InMemoryMLModel used because primary not found
    MOCK = "MOCK"          # MockFraudAdapter / sandbox


@dataclass(frozen=True)
class FraudAMLEvent:
    """Structured observability event emitted once per pipeline assess() call.

    Consumers: ObservabilityAgent, metrics scraper, audit trail caller.
    This dataclass is the single source of truth for one assessment.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    transaction_id: str
    customer_id: str
    entity_type: str                         # "INDIVIDUAL" | "COMPANY"

    # ── Decision ─────────────────────────────────────────────────────────────
    decision: str                            # "APPROVE" | "HOLD" | "BLOCK"
    requires_hitl: bool

    # ── Fraud findings ────────────────────────────────────────────────────────
    fraud_score: int                         # 0-100
    fraud_risk: str                          # LOW / MEDIUM / HIGH / CRITICAL
    fraud_provider: str                      # e.g. "mock", "sardine", "jube"
    fraud_latency_ms: float                  # provider round-trip (nosemgrep: non-monetary)
    app_scam_indicator: str                  # AppScamIndicator value

    # ── AML flags ────────────────────────────────────────────────────────────
    aml_edd_required: bool
    aml_sar_required: bool
    aml_sanctions_block: bool
    aml_velocity_daily_breach: bool
    aml_velocity_monthly_breach: bool
    aml_structuring_signal: bool

    # ── Reason codes (structured policy trace) ────────────────────────────────
    block_reason_codes: list[ReasonCode]
    hold_reason_codes: list[ReasonCode]

    # ── Latency ──────────────────────────────────────────────────────────────
    pipeline_latency_ms: float               # full assess() wall-clock (nosemgrep: non-monetary)

    # ── Model provenance (for drift readiness) ────────────────────────────────
    tm_model_provenance: ModelProvenance     # PRIMARY / FALLBACK / MOCK

    # ── Meta ─────────────────────────────────────────────────────────────────
    assessed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    # ── Guardrail hits ────────────────────────────────────────────────────────
    guardrail_hits: list[str] = field(default_factory=list)  # guardrail names that fired
```

### 4.3 `ObservabilityPort`

```python
# services/fraud/observability_port.py

from __future__ import annotations
from typing import Protocol, runtime_checkable

from services.fraud.fraud_aml_event import FraudAMLEvent


@runtime_checkable
class ObservabilityPort(Protocol):
    """Thin port: pipeline pushes events; observers decide what to do."""

    def emit(self, event: FraudAMLEvent) -> None: ...


class NoopObservabilityPort:
    """Default — no-op; keeps pipeline testable without observability deps."""

    def emit(self, event: FraudAMLEvent) -> None:
        pass
```

---

## 5. Guardrail Rules

### 5.1 `GuardrailPolicy` Protocol

```python
# services/fraud/guardrails.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

from services.fraud.fraud_aml_event import FraudAMLEvent


@dataclass(frozen=True)
class GuardrailViolation:
    guardrail: str
    detail: str
    severity: str  # "HIGH" | "CRITICAL"


class GuardrailPolicy(Protocol):
    """Each guardrail inspects a completed FraudAMLEvent and emits violations.

    Guardrails are advisory: they populate event.guardrail_hits but do NOT
    change the pipeline decision (I-27: propose only).
    """
    name: str

    def check(self, event: FraudAMLEvent) -> list[GuardrailViolation]: ...
```

### 5.2 Concrete Guardrails

#### `LatencyGuardrail`

```python
class LatencyGuardrail:
    """Fires if pipeline latency exceeds SLA (S5-22: <100ms)."""

    name = "LatencyGuardrail"
    sla_ms: float = 100.0  # [PLACEHOLDER] — confirm with infra/SRE

    def check(self, event: FraudAMLEvent) -> list[GuardrailViolation]:
        if event.pipeline_latency_ms > self.sla_ms:
            return [GuardrailViolation(
                guardrail=self.name,
                detail=f"pipeline_latency={event.pipeline_latency_ms:.1f}ms > SLA={self.sla_ms}ms",
                severity="HIGH",
            )]
        return []
```

#### `ScoreAnomalyGuardrail`

```python
class ScoreAnomalyGuardrail:
    """Fires if fraud_score is CRITICAL but decision is APPROVE (impossible by matrix — canary).

    This should never fire in correct code. If it fires, it signals a logic regression.
    """

    name = "ScoreAnomalyGuardrail"

    def check(self, event: FraudAMLEvent) -> list[GuardrailViolation]:
        if event.fraud_risk == "CRITICAL" and event.decision == "APPROVE":
            return [GuardrailViolation(
                guardrail=self.name,
                detail=(
                    f"CRITICAL fraud score ({event.fraud_score}) reached APPROVE — "
                    "invariant violation in decision matrix"
                ),
                severity="CRITICAL",
            )]
        return []
```

#### `FallbackGuardrail`

```python
class FallbackGuardrail:
    """Fires if TM ML model is in FALLBACK mode — signals missing model artefact."""

    name = "FallbackGuardrail"

    def check(self, event: FraudAMLEvent) -> list[GuardrailViolation]:
        from services.fraud.fraud_aml_event import ModelProvenance
        if event.tm_model_provenance == ModelProvenance.FALLBACK:
            return [GuardrailViolation(
                guardrail=self.name,
                detail="TM ML model not found — IsolationForest running on InMemoryMLModel fallback",
                severity="HIGH",
            )]
        return []
```

### 5.3 Guardrail Runner (integration point in `FraudAMLPipeline`)

After constructing `PipelineResult` (at `fraud_aml_pipeline.py:277`), before emitting the observability event:

```python
# Guardrail evaluation (advisory — does not change decision)
guardrail_hits: list[str] = []
for guardrail in self._guardrails:
    violations = guardrail.check(event_draft)
    for v in violations:
        guardrail_hits.append(f"{v.guardrail}:{v.detail}")
        logger.warning("Guardrail hit: %s — %s", v.guardrail, v.detail)
```

`self._guardrails: list[GuardrailPolicy]` injected via constructor (default: all three).

---

## 6. Observability Metrics, Logs, Alerts

### 6.1 Structured Log Line

Replace current free-form `logger.info(...)` at `fraud_aml_pipeline.py:263` with a JSON-serialisable dict:

```python
logger.info(
    "fraud_aml_assess",
    extra={
        "event": "fraud_aml_assess",
        "tx": req.transaction_id,
        "customer": req.customer_id,
        "decision": decision.value,
        "fraud_score": fraud_result.score,
        "fraud_risk": fraud_result.risk.value,
        "fraud_provider": fraud_result.provider,
        "fraud_latency_ms": fraud_latency_ms,
        "app_scam": fraud_result.app_scam_indicator.value,
        "aml_flags": _active_aml_flags(aml_result),
        "pipeline_latency_ms": total_ms,
        "block_codes": [r.code for r in block_reason_codes],
        "hold_codes": [r.code for r in hold_reason_codes],
        "guardrail_hits": guardrail_hits,
        "tm_model_provenance": tm_model_provenance.value,
    },
)
```

### 6.2 Prometheus-Ready Metrics (via `MetricsCollector`)

**File to extend:** `services/observability/metrics_collector.py`

Add a `record_fraud_aml(event: FraudAMLEvent) → None` method (additive, no existing method changed):

| Metric name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `banxe_fraud_pipeline_latency_ms` | Histogram | `decision`, `entity_type` | Full assess() wall-clock |
| `banxe_fraud_score` | Histogram | `risk`, `provider` | Fraud score distribution |
| `banxe_fraud_decisions_total` | Counter | `decision`, `entity_type` | Decision counts |
| `banxe_fraud_guardrail_hits_total` | Counter | `guardrail` | Guardrail violation frequency |
| `banxe_fraud_model_fallback_total` | Counter | — | ML fallback activations |
| `banxe_fraud_hitl_escalations_total` | Counter | `entity_type` | HOLD/BLOCK escalations to HITL |

These are tracked as in-memory accumulators on `MetricsCollector` (same pattern as existing metrics). No Prometheus client library added in B-8.

### 6.3 New `ObservabilityAlert` Types

**File to extend:** `services/observability/observability_agent.py`

Add `register_fraud_event(event: FraudAMLEvent) → None` method:

```python
def register_fraud_event(self, event: "FraudAMLEvent") -> None:
    """Push a pipeline event into the observability alert engine (I-24)."""
    for alert in self._generate_fraud_alerts(event):
        self._alerts.append(alert)  # I-24 append-only
```

New private method `_generate_fraud_alerts(event) → list[ObservabilityAlert]`:

| `alert_type` | `severity` | Trigger condition | `requires_approval_from` |
|--------------|-----------|------------------|--------------------------|
| `FRAUD_SCORING` | `CRITICAL` | `event.fraud_risk == "CRITICAL"` | `COMPLIANCE_OFFICER` |
| `MODEL_FALLBACK` | `HIGH` | `event.tm_model_provenance == ModelProvenance.FALLBACK` | `CTIO` |
| `GUARDRAIL_HIT` | `HIGH` | any entry in `event.guardrail_hits` | `COMPLIANCE_OFFICER` |
| `HITL_ESCALATION` | `HIGH` | `event.requires_hitl == True` | `COMPLIANCE_OFFICER` |

Alert IDs use `hashlib.sha256` on `(alert_type + transaction_id).encode()` — same pattern as existing alerts (line 90).

---

## 7. HITL Approval Gates

The pipeline already gates via `PipelineDecision.HOLD` / `.BLOCK`. B-8 adds no new HITL gate types (those are defined in `services/banking-engine/hitl/gates.py` which has `SAR_FILING`, `AML_THRESHOLD_CHANGE`, `SANCTIONS_REVERSAL`, `PEP_ONBOARDING`).

B-8 **adds** only:

1. **`acknowledge_alert`** (already exists on `ObservabilityAgent:115`) — used for new `FRAUD_SCORING`, `MODEL_FALLBACK`, `GUARDRAIL_HIT`, `HITL_ESCALATION` alerts. No code change needed; the existing gate covers all alert types.

2. **Guardrail threshold changes** are gated via `AML_THRESHOLD_CHANGE` (L4) — adding/modifying guardrail SLA values or score boundaries requires MLRO approval. This is enforced by the `FraudObservabilityConfig` design (§8).

3. **`CTIO` approves `MODEL_FALLBACK` alerts** — this maps to existing `acknowledge_alert()` where `officer` is checked by the caller. No new gate needed; the field `requires_approval_from: "CTIO"` on the alert carries the routing instruction.

---

## 8. Model Governance

### 8.1 `ModelVersionInfo`

**File:** `services/transaction_monitor/scoring/model_event_port.py` (new)

```python
@dataclass(frozen=True)
class ModelVersionInfo:
    name: str           # e.g. "IsolationForest v1"
    version: str        # semver or git SHA of training artefact
    trained_at: str     # ISO-8601 UTC
    features: list[str] # ordered feature names (schema drift detection)
```

`IsolationForestModel` adds a class-level constant:
```python
VERSION_INFO = ModelVersionInfo(
    name="IsolationForest v1",
    version="1.0.0",
    trained_at="2026-01-01T00:00:00Z",  # [PLACEHOLDER] — replace with actual training date
    features=sorted(["velocity_24h", "amount_deviation", "jurisdiction_risk",
                     "round_amount", "crypto_flag", ...]),  # from FeatureExtractor
)
```

### 8.2 `ModelEventPort`

```python
# services/transaction_monitor/scoring/model_event_port.py

from typing import Protocol


class ModelEventPort(Protocol):
    def on_fallback(self, model_path: str) -> None: ...
    def on_load(self, version_info: "ModelVersionInfo") -> None: ...


class NoopModelEventPort:
    def on_fallback(self, model_path: str) -> None:
        pass

    def on_load(self, version_info: "ModelVersionInfo") -> None:
        pass
```

`IsolationForestModel.__init__` gains `model_event_port: ModelEventPort | None = None` (optional, defaults to `NoopModelEventPort`). At `_load()` line 74 (fallback warning):

```python
logger.warning("ML model not found at %s — using fallback", self._model_path)
self._model_event_port.on_fallback(self._model_path)  # NEW — event hook
```

### 8.3 Future LightGBM Adapter (design only — no implementation in B-8)

A `LightGBMModel` that satisfies `MLModelPort` would:
- Accept a model path + `ModelVersionInfo` at `__init__`
- Implement `def score(self, features: dict[str, float]) → float`
- Expose `version_info: ModelVersionInfo` property

No changes to `RiskScorer` needed — it already accepts `ml_model: MLModelPort | None`. Swap the adapter at injection site.

### 8.4 Drift Readiness (advisory — no implementation in B-8)

When `ModelVersionInfo.features` diverges from `FeatureExtractor.FEATURE_NAMES` (future constant), a `FeatureSchemaDriftGuardrail` (B-9+) would fire. B-8 only lays the data structure.

---

## 9. Feature Flags (`FraudObservabilityConfig`)

```python
# services/fraud/fraud_observability_config.py

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class FraudObservabilityConfig:
    """Feature flags for B-8 observability hooks.

    All flags default to False — operator must opt in per environment.
    [PLACEHOLDER] — enable flags via env vars or settings overlay before production.
    """
    emit_structured_events: bool = False        # emit FraudAMLEvent via ObservabilityPort
    enable_latency_guardrail: bool = False       # LatencyGuardrail
    enable_score_anomaly_guardrail: bool = False # ScoreAnomalyGuardrail
    enable_fallback_guardrail: bool = False      # FallbackGuardrail
    enable_fraud_alerts: bool = False            # FRAUD_SCORING / HITL_ESCALATION alerts
    enable_model_fallback_alert: bool = False    # MODEL_FALLBACK alert → CTIO
    enable_guardrail_hit_alert: bool = False     # GUARDRAIL_HIT alert
    latency_sla_ms: float = 100.0               # [PLACEHOLDER] LatencyGuardrail threshold
```

`FraudAMLPipeline.__init__` accepts `obs_config: FraudObservabilityConfig | None = None` (defaults to all-False). Guards wrap every new hook call:

```python
if self._obs_config.emit_structured_events:
    self._obs.emit(event)
```

---

## 10. Minimal-Diff Change Summary

| File | Change type | Lines affected | Risk |
|------|-------------|---------------|------|
| `services/fraud/fraud_aml_pipeline.py` | Additive — new optional constructor args + emit call | +~30 lines near lines 168–177 and 262 | Low — all new params optional; no existing paths changed |
| `services/fraud/fraud_port.py` | No change | — | None |
| `services/observability/observability_agent.py` | Additive — new method `register_fraud_event` + `_generate_fraud_alerts` | +~40 lines | Low — existing `snapshot()` unchanged |
| `services/observability/metrics_collector.py` | Additive — new method `record_fraud_aml` | +~30 lines | Low |
| `services/transaction_monitor/scoring/risk_scorer.py` | Additive — `ModelVersionInfo` constant + optional `ModelEventPort` constructor arg | +~20 lines | Low — scoring logic unchanged |
| `services/fraud/reason_codes.py` | New file | ~90 lines | None (new) |
| `services/fraud/fraud_aml_event.py` | New file | ~60 lines | None (new) |
| `services/fraud/observability_port.py` | New file | ~20 lines | None (new) |
| `services/fraud/guardrails.py` | New file | ~80 lines | None (new) |
| `services/fraud/fraud_observability_config.py` | New file | ~25 lines | None (new) |
| `services/transaction_monitor/scoring/model_event_port.py` | New file | ~30 lines | None (new) |

**Decision matrix untouched** — `fraud_aml_pipeline.py:254–260` (BLOCK > HOLD > APPROVE priority) is read-only for B-8.

---

## 11. Test Plan

### 11.1 `tests/fraud/test_reason_codes.py` (≥15 tests)

```
test_from_fraud_block_has_fraud_domain
test_from_fraud_block_carries_score_contribution
test_from_sanctions_block_references_i06
test_from_app_scam_encodes_indicator_in_code
test_from_edd_hold_references_mlr_2017
test_from_sar_hold_references_poca_2002
test_from_velocity_daily_references_i04
test_from_velocity_monthly_references_i04
test_from_structuring_references_poca_2002
test_reason_code_is_frozen
test_human_text_preserved_verbatim
test_code_is_stable_across_calls
test_multiple_block_codes_distinct
test_policy_ref_is_known_enum_value
test_no_float_in_score_contribution  # score is int
```

### 11.2 `tests/fraud/test_fraud_aml_event.py` (≥15 tests)

```
test_event_is_frozen
test_assessed_at_is_utc_iso8601
test_guardrail_hits_defaults_empty
test_block_reason_codes_serialisable
test_hold_reason_codes_serialisable
test_model_provenance_enum_values
test_pipeline_latency_ms_float_non_monetary
test_fraud_score_is_int
test_decision_string_values
test_entity_type_values
test_aml_flags_all_bool
test_app_scam_indicator_string
test_all_fields_present_on_construction
test_event_created_without_reason_codes_defaults_empty
test_fraud_provider_string_preserved
```

### 11.3 `tests/fraud/test_guardrails.py` (≥15 tests)

```
test_latency_guardrail_fires_above_sla
test_latency_guardrail_silent_below_sla
test_latency_guardrail_fires_at_exact_sla_plus_epsilon
test_score_anomaly_guardrail_fires_on_critical_approve
test_score_anomaly_guardrail_silent_on_critical_block
test_score_anomaly_guardrail_silent_on_critical_hold
test_score_anomaly_guardrail_silent_on_approve_low
test_fallback_guardrail_fires_on_fallback_provenance
test_fallback_guardrail_silent_on_primary_provenance
test_fallback_guardrail_silent_on_mock_provenance
test_all_guardrails_return_list
test_guardrail_violation_frozen
test_guardrail_violation_severity_values
test_guardrail_name_stable
test_noop_obs_port_accepts_event  # NoopObservabilityPort.emit() must not raise
```

### 11.4 `tests/observability/test_fraud_alerts.py` (≥10 tests)

```
test_register_fraud_event_appends_fraud_scoring_alert_on_critical
test_register_fraud_event_appends_hitl_escalation_on_hold
test_register_fraud_event_appends_model_fallback_alert
test_register_fraud_event_appends_guardrail_hit_alert
test_register_fraud_event_no_alert_on_low_approve
test_fraud_alert_requires_approval_from_set
test_fraud_alerts_are_append_only_i24
test_acknowledge_alert_works_for_fraud_alert_type
test_alert_id_deterministic_per_tx
test_alert_log_returns_copy
```

### 11.5 Integration: `FraudAMLPipeline` with observability

Add to existing `tests/fraud/test_fraud_aml_pipeline.py`:

```
test_assess_emits_event_when_config_enabled
test_assess_does_not_emit_when_config_disabled  # all-False default
test_assess_guardrail_hit_recorded_in_event
test_assess_pipeline_latency_ms_positive
test_assess_block_reason_codes_non_empty_on_block
test_assess_hold_reason_codes_non_empty_on_hold
test_assess_approve_both_reason_code_lists_empty
```

### 11.6 Coverage target

- `services/fraud/reason_codes.py`: 100% (pure dataclass + factory methods)
- `services/fraud/fraud_aml_event.py`: 100%
- `services/fraud/guardrails.py`: ≥95%
- `services/observability/observability_agent.py` (existing + new): ≥85%

---

## 12. Duplicate-Risk Check

| Risk | Existing component | B-8 disposition |
|------|--------------------|----------------|
| Explanation generation for AML alerts | `services/transaction_monitor/alerts/explanation_engine.py` — `ExplanationEngine.generate()` produces human-readable text + KB citations for TM alerts | B-8 `ReasonCode.human_text` carries a single string per reason; no KB lookup. No overlap — `ExplanationEngine` is for TM pipeline alerts, `ReasonCode` is for FraudAMLPipeline decision traces. |
| Risk factor reasons | `services/transaction_monitor/models/risk_score.py` — `RiskFactor.explanation: str` | Different domain (TM vs fraud gate). `ReasonCode` does not replace `RiskFactor`. |
| Velocity tracker | `services/aml/redis_velocity_tracker.py`, `services/transaction_monitor/scoring/velocity_tracker.py` | B-8 does not add velocity tracking. `FraudAMLEvent` mirrors existing boolean flags from `TxMonitorResult`. |
| Metrics collection | `services/observability/metrics_collector.py` — `MetricsCollector.collect()` | B-8 adds `record_fraud_aml()` as a new method only. No existing counters modified. |
| Health alerts | `services/observability/observability_agent.py:83–113` — `HEALTH` / `COMPLIANCE` alert types | B-8 adds `FRAUD_SCORING` / `MODEL_FALLBACK` / `GUARDRAIL_HIT` / `HITL_ESCALATION` via new private method. `_generate_alerts()` signature unchanged. |
| Model Protocol | `services/transaction_monitor/scoring/risk_scorer.py:37–41` — `MLModelPort` already defined | B-8 documents it and adds `ModelVersionInfo`. Does not redefine the Protocol. |
| HITL gates | `services/banking-engine/hitl/gates.py` — `SAR_FILING`, `AML_THRESHOLD_CHANGE`, etc. | B-8 reuses `acknowledge_alert()` on `ObservabilityAgent`; no new gate type added. |

---

## 13. Open Items / Placeholders

| ID | Item | Owner | Gate |
|----|------|-------|------|
| OI-B8-1 | `LatencyGuardrail.sla_ms = 100.0` — confirm with infra/SRE | SRE | MLRO/CRO |
| OI-B8-2 | `ModelVersionInfo.trained_at` — replace with actual model training date | ML Ops | CTIO |
| OI-B8-3 | Enable flags in `FraudObservabilityConfig` for staging once smoke tests pass | DevOps | CTIO |
| OI-B8-4 | Prometheus client integration for metric counters (deferred to B-9) | Platform | — |
| OI-B8-5 | ClickHouse schema for `FraudAMLEvent` (for audit trail persistence, deferred) | Data Eng | MLRO |
| OI-B8-6 | `FeatureSchemaDriftGuardrail` implementation (deferred to B-9 after ML Ops sign-off) | ML Ops | MLRO |

---

## 14. Rollout Order

1. Create `services/fraud/reason_codes.py` → tests green → ruff clean
2. Create `services/fraud/fraud_aml_event.py` + `observability_port.py` → tests green
3. Create `services/fraud/guardrails.py` + `fraud_observability_config.py` → tests green
4. Create `services/transaction_monitor/scoring/model_event_port.py` → tests green
5. Extend `services/observability/observability_agent.py` (additive only) → tests green
6. Extend `services/observability/metrics_collector.py` (additive only) → tests green
7. Extend `services/fraud/fraud_aml_pipeline.py` (additive constructor args + emit call, all-False default) → full test suite green
8. Quality gate: `ruff check . && semgrep --config .semgrep/banxe-rules.yml --error && pytest tests/ -x -q --timeout=30`

All flags remain `False` until operator enables them in staging (OI-B8-3).

---

*Blueprint prepared by factory agent (B-8). SANDBOX ONLY. No runtime code modified. Operator reviews and delegates implementation as factory tasks. [I-71: no push.]*
