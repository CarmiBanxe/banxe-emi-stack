-- dbt model: mcp_tool_usage
-- IL-MCP-01 | banxe-emi-stack | 2026-04-11
-- Purpose: Daily MCP tool call analytics for Grafana + executive reporting
-- Source: banxe.mcp_tool_events (ClickHouse, 5yr TTL)
-- Output: Daily tool call counts, error rates, average durations per tool

{{
  config(
    materialized='incremental',
    unique_key='call_date || tool_name',
    on_schema_change='append_new_columns'
  )
}}

WITH daily_stats AS (
    SELECT
        toDate(called_at)                                       AS call_date,
        tool_name                                               AS tool_name,
        count()                                                 AS call_count,
        countIf(status = 'ERROR')                               AS error_count,
        countIf(status = 'OK')                                  AS success_count,
        -- Error rate as percentage (0.00 – 100.00)
        round(
            toDecimal64(countIf(status = 'ERROR'), 2)
            / toDecimal64(count(), 2) * 100,
            2
        )                                                       AS error_rate_pct,
        round(avg(duration_ms), 1)                              AS avg_duration_ms,
        max(duration_ms)                                        AS max_duration_ms,
        min(duration_ms)                                        AS min_duration_ms,
        -- p95 latency (approximate via quantile)
        quantile(0.95)(duration_ms)                             AS p95_duration_ms,
        count(DISTINCT caller_agent)                            AS distinct_callers
    FROM {{ source('banxe', 'mcp_tool_events') }}

    {% if is_incremental() %}
    -- Only process new data on incremental runs
    WHERE called_at >= (
        SELECT coalesce(max(call_date), toDate('2026-01-01'))
        FROM {{ this }}
    )
    {% endif %}

    GROUP BY call_date, tool_name
)

SELECT
    call_date,
    tool_name,
    call_count,
    success_count,
    error_count,
    error_rate_pct,
    avg_duration_ms,
    max_duration_ms,
    min_duration_ms,
    p95_duration_ms,
    distinct_callers,
    -- SLA flag: avg latency > 2000ms is a compliance concern (PS25/12)
    CASE
        WHEN avg_duration_ms > 2000 THEN 'SLA_BREACH'
        WHEN avg_duration_ms > 1000 THEN 'SLA_WARNING'
        ELSE 'SLA_OK'
    END                                                         AS sla_status,
    now()                                                       AS dbt_updated_at
FROM daily_stats
ORDER BY call_date DESC, call_count DESC
