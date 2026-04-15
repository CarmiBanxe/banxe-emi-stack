-- clickhouse_support.sql — Customer Support Block ClickHouse Schema
-- IL-CSB-01 | #114 | banxe-emi-stack
-- TTL: 5 years minimum (I-08, FCA DISP record-keeping + PS22/9 §10)
-- Engine: ReplacingMergeTree (idempotent upserts via ticket_id + updated_at)
-- ClickHouse version: 24.x

-- ──────────────────────────────────────────────────────────────────────────────
-- Table: banxe.support_tickets
-- Purpose: Main ticket store for all customer support interactions
-- FCA basis: DISP 1.3 (prompt handling), DISP 1.10 (record-keeping)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS banxe.support_tickets
(
    -- Identity
    id                      UUID         DEFAULT generateUUIDv4(),
    correlation_id          UUID         DEFAULT generateUUIDv4(),
    customer_id             String,

    -- Content
    subject                 String,
    body                    String,       -- FCA DISP 1.10: full text retained

    -- Classification
    category                Enum8(
        'ACCOUNT'   = 1,
        'PAYMENT'   = 2,
        'KYC'       = 3,
        'FRAUD'     = 4,
        'GENERAL'   = 5
    ),
    priority                Enum8(
        'CRITICAL'  = 1,    -- SLA: 1h
        'HIGH'      = 2,    -- SLA: 4h
        'MEDIUM'    = 3,    -- SLA: 24h
        'LOW'       = 4     -- SLA: 72h
    ),
    status                  Enum8(
        'OPEN'              = 1,
        'IN_PROGRESS'       = 2,
        'AWAITING_CUSTOMER' = 3,
        'ESCALATED'         = 4,
        'RESOLVED'          = 5,
        'CLOSED'            = 6
    ) DEFAULT 'OPEN',

    -- Routing
    assigned_to             String       DEFAULT '',
    channel                 Enum8(
        'API'       = 1,
        'EMAIL'     = 2,
        'TELEGRAM'  = 3,
        'WEB'       = 4,
        'PHONE'     = 5
    ) DEFAULT 'API',
    chatwoot_conversation_id String      DEFAULT '',

    -- SLA
    created_at              DateTime64(3, 'UTC')  DEFAULT now64(),
    updated_at              DateTime64(3, 'UTC')  DEFAULT now64(),
    sla_deadline            DateTime64(3, 'UTC'),
    resolved_at             Nullable(DateTime64(3, 'UTC')),
    resolution_summary      String               DEFAULT '',

    -- Routing metadata
    routing_confidence      Float32              DEFAULT 0.0,
    auto_resolved           UInt8                DEFAULT 0,

    -- Escalation
    escalation_reason       Enum8(
        'NONE'                  = 0,
        'SLA_BREACH'            = 1,
        'CUSTOMER_REQUEST'      = 2,
        'FRAUD_SUSPECTED'       = 3,
        'COMPLAINT_REGULATORY'  = 4,
        'HITL_REQUIRED'         = 5
    ) DEFAULT 'NONE',

    -- DISP (FCA DISP 1.1 — formal complaint flag)
    is_formal_complaint     UInt8        DEFAULT 0,
    disp_category           String       DEFAULT '',
    disp_complaint_id       String       DEFAULT '',  -- IL-022 complaint ID

    -- Audit (I-24 append-only)
    created_by              String       DEFAULT 'system'
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY (customer_id, id)
TTL toDateTime(created_at) + INTERVAL 5 YEAR    -- I-08: minimum 5yr FCA retention
SETTINGS index_granularity = 8192;


-- ──────────────────────────────────────────────────────────────────────────────
-- Table: banxe.sla_events
-- Purpose: Immutable SLA lifecycle log — every status change recorded
-- FCA basis: DISP 1.10 (record of how complaints were handled)
-- Engine: MergeTree (append-only, never updated — I-24)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS banxe.sla_events
(
    id                  UUID         DEFAULT generateUUIDv4(),
    ticket_id           UUID,
    customer_id         String,
    event_type          Enum8(
        'TICKET_CREATED'    = 1,
        'TICKET_ROUTED'     = 2,
        'STATUS_CHANGED'    = 3,
        'SLA_BREACH'        = 4,
        'ESCALATED'         = 5,
        'RESOLVED'          = 6,
        'CLOSED'            = 7,
        'CSAT_SUBMITTED'    = 8
    ),
    old_status          String       DEFAULT '',
    new_status          String       DEFAULT '',
    agent               String       DEFAULT 'system',  -- which agent fired the event
    priority            String       DEFAULT '',
    sla_deadline        DateTime64(3, 'UTC'),
    occurred_at         DateTime64(3, 'UTC')  DEFAULT now64(),
    metadata            String       DEFAULT '{}'        -- JSON blob for extra context
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (ticket_id, occurred_at)
TTL toDateTime(occurred_at) + INTERVAL 5 YEAR    -- I-08
SETTINGS index_granularity = 8192;


-- ──────────────────────────────────────────────────────────────────────────────
-- Table: banxe.csat_scores
-- Purpose: Customer satisfaction and NPS scores — PS22/9 §10 Consumer Duty
-- FCA basis: PS22/9 §10 (outcome monitoring), DISP 1.10 (records)
-- TTL: 7 years (same as FCA DISP records — exceeds I-08 minimum)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS banxe.csat_scores
(
    id              UUID         DEFAULT generateUUIDv4(),
    ticket_id       UUID,
    customer_id     String,
    category        Enum8(
        'ACCOUNT'   = 1,
        'PAYMENT'   = 2,
        'KYC'       = 3,
        'FRAUD'     = 4,
        'GENERAL'   = 5
    ),
    -- CSAT: 1-5 scale
    csat_score      UInt8,        -- 1 (very dissatisfied) → 5 (very satisfied)
    -- NPS: 0-10 scale (nullable — only collected in periodic surveys)
    nps_score       Nullable(UInt8),  -- 0-6 detractor / 7-8 passive / 9-10 promoter
    -- Free text (PII — masked in exports, full text retained for audit)
    feedback_text   String       DEFAULT '',
    positive_outcome UInt8       DEFAULT 0,   -- csat_score ≥ 4 (PS22/9 §10 threshold)
    submitted_at    DateTime64(3, 'UTC')  DEFAULT now64(),
    -- Channel of the original ticket
    channel         String       DEFAULT ''
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(submitted_at)
ORDER BY (customer_id, ticket_id, submitted_at)
TTL toDateTime(submitted_at) + INTERVAL 7 YEAR
SETTINGS index_granularity = 8192;


-- ──────────────────────────────────────────────────────────────────────────────
-- Materialised view: banxe.support_sla_daily
-- Purpose: Daily SLA performance aggregate for Consumer Duty reporting
-- Used by: Metabase / Grafana dashboards, FCA outcome testing
-- ──────────────────────────────────────────────────────────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS banxe.support_sla_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (day, category, priority)
AS
SELECT
    toDate(created_at)                                   AS day,
    category,
    priority,
    count()                                              AS total_tickets,
    countIf(status IN ('RESOLVED', 'CLOSED'))            AS resolved_tickets,
    countIf(escalation_reason = 'SLA_BREACH')            AS sla_breaches,
    countIf(auto_resolved = 1)                           AS auto_resolved,
    countIf(is_formal_complaint = 1)                     AS formal_complaints,
    avg(toUnixTimestamp(resolved_at) -
        toUnixTimestamp(created_at))                     AS avg_resolution_seconds
FROM banxe.support_tickets
WHERE status IN ('RESOLVED', 'CLOSED')
GROUP BY day, category, priority;
