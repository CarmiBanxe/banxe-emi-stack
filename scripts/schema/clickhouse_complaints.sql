-- clickhouse_complaints.sql — Consumer Duty / DISP complaints schema
-- IL-022 | FCA Consumer Duty DISP 1.4 (8-week SLA) | banxe-emi-stack
-- TTL: 7 years (FCA DISP record-keeping requirement)

CREATE TABLE IF NOT EXISTS banxe.complaints
(
    id                  UUID         DEFAULT generateUUIDv4(),
    customer_id         String,
    category            Enum8(
        'PAYMENT'         = 1,
        'ACCOUNT'         = 2,
        'CHARGES'         = 3,
        'SERVICE'         = 4,
        'FRAUD'           = 5,
        'DATA_PRIVACY'    = 6,
        'OTHER'           = 7
    ),
    description         String,
    status              Enum8(
        'OPEN'            = 1,
        'INVESTIGATING'   = 2,
        'RESOLVED'        = 3,
        'FOS_ESCALATED'   = 4
    ) DEFAULT 'OPEN',
    created_at          DateTime     DEFAULT now(),
    sla_deadline        DateTime,     -- created_at + 56 days (8 weeks, DISP 1.4.1R)
    resolved_at         Nullable(DateTime),
    resolution_summary  String       DEFAULT '',
    assigned_to         String       DEFAULT '',
    channel             Enum8(
        'TELEGRAM'        = 1,
        'EMAIL'           = 2,
        'PHONE'           = 3,
        'WEB'             = 4,
        'API'             = 5
    ) DEFAULT 'API',
    fos_reference       String       DEFAULT '',  -- FOS case ref if escalated
    created_by          String       DEFAULT 'system'
)
ENGINE = MergeTree()
ORDER BY (created_at, customer_id)
TTL created_at + INTERVAL 7 YEAR
SETTINGS index_granularity = 8192;


-- Append-only audit trail (I-24: no UPDATE/DELETE)
CREATE TABLE IF NOT EXISTS banxe.complaint_events
(
    event_id        UUID         DEFAULT generateUUIDv4(),
    complaint_id    UUID,
    event_type      Enum8(
        'OPENED'          = 1,
        'STATUS_CHANGED'  = 2,
        'NOTE_ADDED'      = 3,
        'ASSIGNED'        = 4,
        'RESOLVED'        = 5,
        'FOS_ESCALATED'   = 6,
        'SLA_WARNING'     = 7,
        'SLA_BREACHED'    = 8
    ),
    old_status      String       DEFAULT '',
    new_status      String       DEFAULT '',
    note            String       DEFAULT '',
    actor           String       DEFAULT 'system',
    occurred_at     DateTime     DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (complaint_id, occurred_at)
TTL occurred_at + INTERVAL 7 YEAR
SETTINGS index_granularity = 8192;
