-- Migration 005: MCP Tool Events table
-- IL-MCP-01 | banxe-emi-stack | 2026-04-11
-- Purpose: Track MCP tool call metrics for monitoring (Grafana mcp-server.json)
--          and health checks (mcp_health_workflow.py)
-- TTL: 5 years (I-08: FCA audit trail minimum)

CREATE TABLE IF NOT EXISTS banxe.mcp_tool_events
(
    -- Tool identification
    tool_name     String          COMMENT 'MCP tool function name (e.g. get_recon_status)',
    called_at     DateTime        COMMENT 'UTC timestamp of tool invocation',

    -- Performance
    duration_ms   UInt32          COMMENT 'Tool execution duration in milliseconds',

    -- Result
    status        String          COMMENT 'OK or ERROR',
    error_message Nullable(String) COMMENT 'Error description if status = ERROR',

    -- Caller
    caller_agent  String          COMMENT 'Agent ID or session that called the tool',

    -- FCA audit fields
    inserted_at   DateTime DEFAULT now() COMMENT 'Row insertion timestamp (immutable)'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(called_at)
ORDER BY (called_at, tool_name)
TTL called_at + INTERVAL 1825 DAY  -- 5 years (I-08: FCA minimum retention) -- nosemgrep: banxe-clickhouse-ttl-reduce
SETTINGS index_granularity = 8192;

-- MCP Health Events table (health workflow results)
CREATE TABLE IF NOT EXISTS banxe.mcp_health_events
(
    checked_at          String   COMMENT 'ISO-8601 UTC timestamp from health check',
    status              String   COMMENT 'healthy | degraded | unhealthy',
    tools_checked       UInt16   COMMENT 'Total number of tools validated',
    tools_failed_count  UInt16   COMMENT 'Number of tools that failed validation',
    tools_failed_names  String   COMMENT 'Comma-separated list of failed tool names',
    error_message       String   COMMENT 'Import error if server not importable',
    inserted_at         DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY inserted_at
TTL inserted_at + INTERVAL 1825 DAY; -- nosemgrep: banxe-clickhouse-ttl-reduce

-- Materialized view: daily MCP tool stats (for dbt model input)
CREATE MATERIALIZED VIEW IF NOT EXISTS banxe.mcp_daily_tool_stats
ENGINE = SummingMergeTree()
ORDER BY (call_date, tool_name)
AS
SELECT
    toDate(called_at)   AS call_date,
    tool_name           AS tool_name,
    count()             AS call_count,
    countIf(status = 'ERROR') AS error_count,
    avg(duration_ms)    AS avg_duration_ms,
    max(duration_ms)    AS max_duration_ms
FROM banxe.mcp_tool_events
GROUP BY call_date, tool_name;
