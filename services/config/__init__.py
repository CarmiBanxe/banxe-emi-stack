"""
config — Shared runtime configuration + Config-as-Data
banxe-emi-stack

Env-var constants (backwards-compatible with services.config.CLICKHOUSE_DB etc.)
+ Config-as-Data submodules: config_port, config_service.
"""

from __future__ import annotations

import os

# ── ClickHouse ────────────────────────────────────────────────────────────────
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "9000"))
CLICKHOUSE_DB = os.environ.get("CLICKHOUSE_DB", "banxe")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")

# ── Midaz CBS ─────────────────────────────────────────────────────────────────
MIDAZ_BASE_URL = os.environ.get("MIDAZ_BASE_URL", "http://localhost:8095")
MIDAZ_ORG_ID = os.environ.get("MIDAZ_ORG_ID", "")
MIDAZ_LEDGER_ID = os.environ.get("MIDAZ_LEDGER_ID", "")
MIDAZ_TOKEN = os.environ.get("MIDAZ_TOKEN", "")

# ── Statements ────────────────────────────────────────────────────────────────
STATEMENT_DIR = os.environ.get("STATEMENT_DIR", "/data/banxe/statements")
ADORSYS_PSD2_URL = os.environ.get("ADORSYS_PSD2_URL", "http://localhost:8888")

# ── Alerting ──────────────────────────────────────────────────────────────────
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")

# ── FCA Reporting ─────────────────────────────────────────────────────────────
FIN060_OUTPUT_DIR = os.environ.get("FIN060_OUTPUT_DIR", "/data/banxe/reports/fin060")
FCA_REGDATA_URL = os.environ.get("FCA_REGDATA_URL", "https://regdata.fca.org.uk")
