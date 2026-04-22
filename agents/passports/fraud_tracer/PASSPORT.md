# PASSPORT — FraudTracerAgent
**IL:** IL-TRC-01
**Phase:** 54C
**Sprint:** 39

## Identity
- **Agent ID:** fraud-tracer-agent-v1
- **Domain:** Real-Time Fraud Scoring
- **Autonomy Level:** L4 (Human Only for score > 0.8)
- **HITL Gate:** FRAUD_ANALYST for fraud score >= 0.8

## Capabilities
- `trace()` — real-time fraud scoring (target: p99 < 100ms)
- Rules: blocked jurisdiction (I-02), EDD threshold (I-04), velocity check
- `check_velocity()` — Redis-backed velocity window check

## Constraints
- MUST NOT auto-block transactions without FRAUD_ANALYST (I-27)
- MUST NOT use float for scores (I-01)
- MUST NOT delete trace_log (I-24)
- BT-009: ML model scoring raises NotImplementedError (P1)

## Ports
- `VelocityPort` -> `InMemoryVelocityPort` (stub) / real Redis
- BT-009: `ml_model_score()` -> raises NotImplementedError

## Audit
- `TracerEngine.trace_log` — append-only (I-24)
- `FraudTracerAgent.proposals` — append-only (I-24)
