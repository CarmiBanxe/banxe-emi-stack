-- Migration 006: Agent decision-lineage records table (ADR-046)
-- FU-2 | banxe-emi-stack | 2026-06-14
-- Purpose: Durable, queryable sink for AgentDecisionRecord emitted by the L2
--          client-facing agent masks (services/agents/_lineage.py). This is the
--          ClickHouse backing store for ClickHouseDecisionRecorder.
-- Scope:   ADDITIVE only — creates one new append-only table. No existing table
--          is dropped or altered. The Intent Layer stays dark (INTENT_LAYER_ENABLED
--          remains false); this table is written only when DECISION_RECORDER=clickhouse.
-- TTL:     5 years (I-08 / FCA audit-trail minimum retention).
--
-- R-SEC (ADR-021): rows carry opaque governance metadata ONLY — never
--          seed/entropy/key/password/plaintext/ciphertext. Secret material is
--          never recorded (see _lineage.py R-SEC note).

CREATE TABLE IF NOT EXISTS banxe.decision_records
(
    -- ── Identity (AgentDecisionRecord.record_id / .timestamp / .agent_id) ──────
    record_id           String          COMMENT 'AgentDecisionRecord.record_id (unique per decision)',
    timestamp           DateTime64(3)   COMMENT 'UTC decision time (ADR-046)',
    agent_id            LowCardinality(String) COMMENT 'Emitting mask agent id',

    -- ── Decision context (ADR-046 schema) ────────────────────────────────────
    triggering_event    String          COMMENT 'What triggered the masked action',
    intent              LowCardinality(String) COMMENT 'Resolved mask intent (scope)',
    policies_evaluated  Array(String)   COMMENT 'L3 policies evaluated for this decision',
    compliance_result   LowCardinality(String) COMMENT 'PASS | FAIL | ESCALATE | N/A (band)',
    reasoning_summary   String          COMMENT 'Opaque human-readable rationale',
    confidence_score    Float64         COMMENT 'Decision confidence [0,1]',
    action_taken        String          COMMENT 'The action the mask performed',
    correlation_id      String          COMMENT 'Process/run correlation handle',

    -- ── Human-in-the-loop (ADR-046) ──────────────────────────────────────────
    human_reviewed_by   Nullable(String) COMMENT 'Reviewer id when HITL applied, else NULL',
    human_override_flag UInt8           COMMENT '1 when a human reviewed/overrode, else 0',
    escalated_to        Nullable(String) COMMENT 'Role escalated to (MLRO/DPO/AML), else NULL',

    -- ── Cost lineage (ADR-047) — never float for money; Decimal only ──────────
    cost_tokens         UInt64          COMMENT 'Total tokens for this invocation',
    cost_amount         Decimal(38, 18) COMMENT 'Monetary cost (Decimal — never float)',
    budget_window_ref   LowCardinality(String) COMMENT 'Rolling cost-window ref',
    budget_breach_flag  LowCardinality(String) COMMENT 'NONE | WARN | BREACH',
    input_tokens        Nullable(UInt64) COMMENT 'Prompt-token split (refines cost_tokens)',
    output_tokens       Nullable(UInt64) COMMENT 'Completion-token split (refines cost_tokens)',

    -- ── WORM / immutable storage handle (ADR-046 §D5) ─────────────────────────
    immutable_storage_ref Nullable(String) COMMENT 'WORM storage handle for the record',

    -- ── Audit insertion stamp (immutable) ─────────────────────────────────────
    inserted_at         DateTime DEFAULT now() COMMENT 'Row insertion timestamp (immutable)'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, agent_id, record_id)
TTL toDateTime(timestamp) + INTERVAL 1825 DAY  -- 5 years (I-08: FCA minimum retention) -- nosemgrep: banxe-clickhouse-ttl-reduce
SETTINGS index_granularity = 8192;
