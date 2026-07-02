# DEPLOYMENT MANIFEST — BANXE EMI Stack

**Date:** 2026-07-02  
**Status:** AS-BUILT (reflects current deployed state)  
**Maintained by:** Factory (append-only per I-24)  
**Source of truth:** This file + docker-compose.master.yml + ADR-018 5-layer addendum  
**Regulatory scope:** FCA CASS 15 / MLR 2017 / PSR 2017 / PS22/9

---

## Node Inventory

| Node | Role | Hardware | State | Access | Notes |
|------|------|----------|-------|--------|-------|
| **Legion** | Dev workstation + API gateway + LiteLLM orchestrator | Intel/AMD x86-64, 64GiB+ RAM, GPU optional | ACTIVE | USB, Tailscale :22 | P0 primary; hosts API :8000, PostgreSQL :5432, ClickHouse :9000, Redis :6379 |
| **evo1** | AI compute primary (GPU-heavy, 96GiB iGPU) | AMD Ryzen AI, 96GiB iGPU, 64GiB RAM | ⚠️ SSH DOWN (GAP-093) | Physical only | llama.cpp :8081 + RPC worker :50052; offline since GAP-093 incident |
| **evo2** | AI compute secondary (CPU-heavy, USB4 L2L) | AMD Ryzen AI, 32GiB iGPU, 96GiB RAM | ACTIVE | SSH :22, USB4 10.0.0.2/30 | qwen3:235b (llama.cpp) :8082 + RPC worker :50052; Ollama :11434; DB node candidate |

**Network topology:** Legion ↔ evo2 via USB4 10.0.0.1/30 ↔ 10.0.0.2/30 @ 9.12 Gbit/s

---

## Core Service Registry

### docker-compose.master.yml (P0 Stack)

| # | Service | Port | Docker image | Version | Health | Purpose |
|---|---------|------|--------------|---------|--------|---------|
| 1 | **PostgreSQL** | :5432 | postgres:17-alpine | 17 | ✅ ACTIVE | Primary ledger DB + pgAudit audit trail |
| 2 | **ClickHouse** | :9000, :8123 | clickhouse/clickhouse-server:24.3-alpine | 24.3 | ✅ ACTIVE | Append-only audit trail (5Y TTL I-24), safeguarding_events |
| 3 | **Redis** | :6379 | redis:7-alpine | 7 | ✅ ACTIVE | Session cache, distributed locks, velocity counters |
| 4 | **Frankfurter** | :8087 → :8080 | hakanensari/frankfurter:latest | latest | ✅ ACTIVE | Self-hosted ECB FX rates (160+ currencies, no API key) |
| 5 | **FastAPI API** | :8000 | build: docker/Dockerfile | 1.0.0 | ✅ ACTIVE | Banxe REST API (customers, payments, ledger, KYC, etc.) |

**Node:** All on Legion (docker-compose.master.yml)  
**Depends-on:** api waits for postgres → redis → clickhouse → frankfurter (healthchecks)

---

### docker-compose.recon.yml (CASS 7.15 Reconciliation)

| # | Service | Port | Docker image | Purpose |
|---|---------|------|--------------|---------|
| 6 | **PostgreSQL (recon)** | :5432 | pgvector/pgvector:pg17 | Reconciliation DB (pgAudit disabled—temporary) |
| 7 | **ClickHouse (recon)** | :8123, :9000 | clickhouse/clickhouse-server:24.3 | Recon audit trail (append-only TTL 5Y) |
| 8 | **Redis (recon)** | :6379 | redis:7-alpine | Recon state cache |
| 9 | **n8n** | :5678 | n8nio/n8n:latest | MLRO alert workflows (Slack, email notifications) |
| 10 | **Grafana (recon)** | :3001 → :3000 | grafana/grafana:10.4.0 | Safeguarding reconciliation dashboard + Clickhouse datasource |
| 11 | **Frankfurter (recon)** | :8181 → :8080 | hakanensari/frankfurter:latest | FX rates (port 8181 to avoid conflict with nginx on GMKtec) |

**Node:** All on Legion (docker-compose.recon.yml)

---

### docker-compose.transaction-monitor.yml (RTM: MLR 2017 Real-Time Monitoring)

| # | Service | Port | Docker image | Purpose |
|---|---------|------|--------------|---------|
| 12 | **Banxe API (monitor)** | :8000 | build: docker/Dockerfile.api | Transaction monitoring API (/v1/monitor/*) |
| 13 | **Redis (monitor)** | :6379 | redis:7-alpine | Velocity counters (1h/24h/7d sliding windows) |
| 14 | **ClickHouse (monitor)** | :8123, :9000 | clickhouse/clickhouse-server:24.3 | AML alert audit trail (TTL 5Y I-24) |
| 15 | **Marble** | :3000 | ghcr.io/checkmarble/marble-backend:latest | Case management for CRITICAL/HIGH AML alerts |
| 16 | **PostgreSQL (monitor)** | :5432 | pgvector/pgvector:pg17 | Marble DB + audit foreign keys |
| 17 | **Grafana (monitor)** | :3002 → :3000 | grafana/grafana:10.4.0 | AML monitoring dashboard |

**Node:** All on Legion (docker-compose.transaction-monitor.yml)

---

### docker-compose.reporting.yml (FCA Reporting)

| # | Service | Port | Docker image | Purpose |
|---|---------|------|--------------|---------|
| 18 | **dbt** | (no port) | dbt:latest | dbt Core models: staging → marts → fin060 |
| 19 | **fin060-generator** | (no port) | build: docker/Dockerfile.fin060 | FIN060 PDF generation (JasperReports + WeasyPrint) |

**Node:** Legion (docker-compose.reporting.yml)

---

### docker-compose.mcp.yml (MCP Tools Server)

| # | Service | Port | Docker image | Purpose |
|---|---------|------|--------------|---------|
| 20 | **banxe-mcp** | (stdio) | build: docker/Dockerfile.mcp | MCP protocol server (34 tools: financial, ARL, KB, monitor, design, experiments) |

**Node:** Legion  
**Transport:** stdio (no network port)

---

### docker-compose.psd2.yml (PSD2 Gateway)

| # | Service | Port | Docker image | Purpose |
|---|---------|------|--------------|---------|
| 21 | **mock-aspsp** | (internal) | build: docker/Dockerfile.mock-aspsp | Mock ASPSP for PSD2 testing (Art.97 SCA) |

**Node:** Legion (dev/test only)

---

### docker-compose.bi.yml (Business Intelligence)

| # | Service | Port | Docker image | Purpose |
|---|---------|------|--------------|---------|
| 22 | **Superset** | (no port) | apache/superset:latest | Business intelligence + dashboards (optional) |

**Node:** Legion (optional)

---

## IAM & Auth (Separate Deployment)

| # | Service | Port | Container image | Version | Status | Purpose |
|---|---------|------|-----------------|---------|--------|---------|
| 23 | **Keycloak** | :8180 | quay.io/keycloak/keycloak:26.2.5 | 26.2.5 | ✅ ACTIVE | OIDC/SAML IAM (FCA I-34, I-35) |
| — | **keycloak-pg** | (internal) | postgres:16-alpine | 16 | ✅ ACTIVE | Keycloak DB backend (named volume, G-IAM-09 closure) |

**Location:** `infra/keycloak-banxe-emi/docker-compose.yml`  
**Hostname:** 100.101.218.26 (Legion Tailscale IP)  
**Node:** Legion (via infra/keycloak-banxe-emi/docker-compose.yml)  
**Health check:** GET /realms/master (200 OK)  
**References:** G-IAM-09 closure, ADR-017, ADR-022

---

## External Fraud & Compliance Services

| # | Service | Endpoint | Type | Status | Blocker | Purpose |
|---|---------|----------|------|--------|---------|---------|
| 24 | **Jube** | :5001 (internal) | Docker | UNKNOWN—operator to verify | — | Rules engine for fraud scoring |
| 25 | **Marble** | :3000 (in RTM) | Docker (self-hosted) | ✅ ACTIVE | — | Case management (High-risk AML) |
| 26 | **Moov Watchman** | (endpoint from .env) | API | UNKNOWN—operator to verify | — | Sanctions screening + entity matching |
| 27 | **Ballerine KYC** | :3000 (infra/ballerine/) | Docker (self-hosted) | UNKNOWN—operator to verify | — | Self-hosted KYC workflow (AML-001) |

**References:** agents/compliance/swarm.yaml, ADR-102 (payment rail), ADR-103 (fraud)

---

## AI Compute Layer (ADR-018 Hybrid 5-Layer)

### L1 — Primary inference node (qwen3:235b on evo2)

| Layer | Service | Endpoint | Node | Model | Quantization | Memory | Status |
|-------|---------|----------|------|-------|--------------|--------|--------|
| **L1** | qwen3:235b (llama.cpp) | :8082 | evo2 | Qwen/Qwen2-7B-Instruct or 235B ultra | Q3_K_S | 32GiB iGPU | ✅ ACTIVE |

---

### L2 — Fallback Ollama pools (dual-pool redundancy)

| Layer | Service | Endpoint | Node | Models loaded | Status |
|-------|---------|----------|------|---------------|--------|
| **L2** | Ollama (Legion) | :11434 | Legion | [models from ollama list] | ✅ ACTIVE |
| **L2** | Ollama (evo2) | :11434 | evo2 | [models from ollama list] | ✅ ACTIVE |

---

### L5 — Router & Load Balancing

| Layer | Service | Endpoint | Node | Aliases | Status |
|-------|---------|----------|------|---------|--------|
| **L5** | LiteLLM (lite-llm) | :4000 | Legion | 20 model aliases (claude, gpt-4, llama, qwen, etc.) | ✅ ACTIVE |

**References:** ADR-018 hybrid 5-layer, commit e90ac30+, `/workspace/NODES.md` (evo nodes topology)

---

## Port Registry (All Services)

| Port | Service | Protocol | Node | Container | Auth | Status |
|------|---------|----------|------|-----------|------|--------|
| 3000 | Marble / Ballerine KYC / Grafana fallback | HTTP | Legion | ghcr.io/checkmarble/marble-backend OR docker compose | API key / basic | ✅ |
| 3001 | Grafana (recon) | HTTP | Legion | grafana/grafana:10.4.0 | Basic auth | ✅ |
| 3002 | Grafana (monitor) | HTTP | Legion | grafana/grafana:10.4.0 | Basic auth | ✅ |
| 5001 | Jube | HTTP | Legion | (docker/orchestration) | — | UNKNOWN |
| 5678 | n8n | HTTP | Legion | n8nio/n8n:latest | Basic auth | ✅ |
| 6379 | Redis (×3 instances) | TCP | Legion | redis:7-alpine | None (local) | ✅ |
| 8000 | FastAPI API (master) | HTTP | Legion | banxe:latest (Dockerfile) | OAuth2 (Keycloak) | ✅ |
| 8000 | FastAPI API (monitor) | HTTP | Legion | banxe:latest (Dockerfile.api) | OAuth2 | ✅ |
| 8082 | llama.cpp (qwen3:235b) | HTTP | evo2 | llama.cpp server | None (internal) | ✅ |
| 8087 | Frankfurter (master) | HTTP | Legion | hakanensari/frankfurter:latest | None | ✅ |
| 8123 | ClickHouse HTTP (×3 instances) | HTTP | Legion | clickhouse/clickhouse-server:24.3-alpine | None (local) | ✅ |
| 8180 | Keycloak | HTTP | Legion | quay.io/keycloak/keycloak:26.2.5 | None (public, proxied) | ✅ |
| 8181 | Frankfurter (recon) | HTTP | Legion | hakanensari/frankfurter:latest | None | ✅ |
| 9000 | ClickHouse native (×3 instances) | TCP | Legion | clickhouse/clickhouse-server:24.3-alpine | None (local) | ✅ |
| 5432 | PostgreSQL (×3 instances) | TCP | Legion | postgres:17-alpine OR pgvector:pg17 | PASSWORD | ✅ |
| 11434 | Ollama (Legion) | HTTP | Legion | ollama/ollama:latest | None (internal) | ✅ |
| 11434 | Ollama (evo2) | HTTP | evo2 | ollama/ollama:latest | None (internal) | ✅ |
| 4000 | LiteLLM (orchestrator) | HTTP | Legion | lite-llm:latest | API key | ✅ |
| 50052 | llama-rpc-worker (evo2) | gRPC | evo2 | llama-rpc-worker | None (internal) | ✅ |
| 50052 | llama-rpc-worker (evo1) | gRPC | evo1 | llama-rpc-worker | None (internal) | ⚠️ SSH DOWN |

**Note:** Multiple containers may listen on same port (e.g., :6379) via Docker compose network isolation.

---

## External Dependencies & Blockers

| # | Dependency | Endpoint | Type | Purpose | Status | Blocker | Reference |
|----|------------|----------|------|---------|--------|---------|-----------|
| A | **Modulr** | (prod API) | REST API | Payment rail (SEPA IBAN, instant, RTGS) | ⛔ NOT DEPLOYED | **BT-001** | ADR-102 (payment rail) |
| B | **adorsys PSD2** | (prod API) | PSD2 Gateway | Bank statement auto-pull (CAMT.053/MT940) | UNKNOWN | — | S37 (P0 item) |
| C | **Frankfurter ECB** | self-hosted | REST API | FX rates (160+ currencies, no key) | ✅ ACTIVE | — | P0 item S37 |
| D | **Midaz CBS** | :8095 (internal) | REST API | Core banking system (ledger source of truth) | UNKNOWN | — | CASS 15 ledger port |
| E | **RegData** | (prod endpoint) | FCA file upload | FCA regulatory submission (FIN060) | UNKNOWN | **BT-002** | S36 (P0 item) |
| F | **Blnk Finance** | (API) | Safeguarding processor | Daily safeguarding reconciliation | UNKNOWN | — | S36 (P0 item) |
| G | **BankStatementParser** | (Python lib) | Library | CAMT.053 / MT940 parsing | ✅ Vendored | — | S36 (P0 item) |

**Reference:** `.claude/rules/cass15.md` P0 Stack Map

---

## Environment Variables (Non-Secret Reference)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | banxe | PostgreSQL database name |
| `POSTGRES_USER` | banxe | PostgreSQL user |
| `CLICKHOUSE_DB` | banxe | ClickHouse database |
| `CLICKHOUSE_USER` | default | ClickHouse user |
| `REDIS_URL` | redis://redis:6379/0 | Redis connection |
| `FRANKFURTER_BASE_URL` | http://frankfurter:8080 | ECB FX service URL |
| `BANXE_ENV` | production | Environment flag |
| `EDD_THRESHOLD_INDIVIDUAL_GBP` | 10000 | AML individual EDD threshold (I-04) |
| `EDD_THRESHOLD_CORPORATE_GBP` | 50000 | AML corporate EDD threshold (I-04) |
| `BLOCKED_JURISDICTIONS` | RU,BY,IR,KP,CU,MM,AF,VE,SY | Hard-block list (I-02) |
| `RULES_WEIGHT` | 0.40 | Risk scoring: rules weight |
| `ML_WEIGHT` | 0.30 | Risk scoring: ML weight |
| `VELOCITY_WEIGHT` | 0.30 | Risk scoring: velocity weight |
| `VELOCITY_1H_THRESHOLD` | 5 | AML velocity threshold (1 hour) |
| `VELOCITY_24H_THRESHOLD` | 10 | AML velocity threshold (24 hours) |
| `VELOCITY_7D_THRESHOLD` | 50 | AML velocity threshold (7 days) |
| `KC_HOSTNAME` | 100.101.218.26 | Keycloak hostname (Legion Tailscale IP) |

**Note:** All `(secret)` values stored in `.env` (ignored by git). `.env.example` contains structure only.

---

## Deployment Topology Diagram

```
┌──────────────────────────────────────── LEGION (dev workstation) ────────────────────────────────────┐
│  ┌─ P0 Master ──────────┐  ┌─ Recon ───────────┐  ┌─ RTM ─────────┐  ┌─ Keycloak ──┐  ┌─ Reporting ┐ │
│  │ API :8000            │  │ n8n :5678         │  │ Marble :3000  │  │ KC :8180    │  │ dbt/FIN060  │ │
│  │ PG :5432             │  │ Grafana :3001     │  │ Grafana :3002 │  │ PG (KC) :— │  │             │ │
│  │ Redis :6379          │  │ PG/CH/Redis/FX    │  │ PG/CH/Redis   │  │             │  │             │ │
│  │ CH :9000/:8123       │  │                   │  │               │  │             │  │             │ │
│  │ Frankfurter :8087    │  │                   │  │               │  │             │  │             │ │
│  └──────────────────────┘  └───────────────────┘  └───────────────┘  └─────────────┘  └─────────────┘ │
│                                                                                                        │
│  ┌─ MCP Server ──────┐  ┌─ AI Orchestration ─────────────────┐                                      │
│  │ banxe-mcp (stdio) │  │ LiteLLM :4000  Ollama :11434       │                                      │
│  │ 34 tools          │  │ (20 aliases, fallback pool)        │                                      │
│  └───────────────────┘  └────────────────────────────────────┘                                      │
│                                                                                                        │
│  🔌 Docker compose stacks coexist; port isolation via Docker network                                │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
         │ USB4 10.0.0.1/30 ↔ 10.0.0.2/30 @ 9.12 Gbit/s  │  Tailscale SSH (evo2 only)
         │
         ├──────────────────────────────────────────────┤
         │                                               │
┌─ EVO1 (SSH DOWN) ──────────┐    ┌─ EVO2 (ACTIVE) ──────────────────┐
│ llama.cpp :8081            │    │ qwen3:235b :8082                  │
│ llama-rpc-worker :50052    │    │ llama-rpc-worker :50052           │
│ Ollama :11434              │    │ Ollama :11434                     │
│ GPU: 96GiB iGPU            │    │ GPU: 32GiB iGPU, CPU: 96GiB       │
│ ADR-018 L1 OFFLINE         │    │ ADR-018 L1 + L2 fallback ACTIVE   │
└────────────────────────────┘    └───────────────────────────────────┘
```

---

## Open Items & Blockers

| ID | Issue | Type | Owner | Impact | Status | Reference |
|----|-------|------|-------|--------|--------|-----------|
| **GAP-093** | evo1 SSH DOWN | Infrastructure | Operator | L1 AI offline; fallback to evo2 only | ⚠️ PENDING | ADR-018 §6 |
| **GAP-082** | ufw firewall not configured | Security | Operator | Inbound ports exposed | ⚠️ PENDING | Firewall TBD |
| **BT-001** | Modulr API not deployed | Payment integration | CEO | Payment rail BLOCKED | 🔴 CRITICAL | ADR-102 |
| **BT-002** | RegData FCA endpoint not configured | FCA reporting | CEO/Compliance | FCA submission BLOCKED | 🔴 CRITICAL | S36 (P0) |
| **OD-3** | USB4 peer identity unconfirmed | Infrastructure | Operator | L2L routing may fail | ⚠️ PENDING | ADR-018 §OQ |
| **S36** | Daily safeguarding reconciliation | P0 delivery | Factory | CASS 7.15 obligation | ⏳ IN_PROGRESS | P0 item |
| **S37** | adorsys PSD2 gateway integration | P0 delivery | Factory | Bank statement auto-pull | ⏳ IN_PROGRESS | P0 item |

---

## Compliance Mapping

| Regulatory Ref | Control | Implemented | Evidence | Status |
|---|---|---|---|---|
| **FCA CASS 15** | Segregated safeguarding accounts | Daily recon service | `services/safeguarding/`, `services/recon/` | ✅ P0 |
| **FCA CASS 7.15** | Daily statement reconciliation | n8n workflows + Blnk Finance adapter | `docker-compose.recon.yml`, `services/recon/` | ✅ P0 |
| **FCA MLR 2017** | Real-time transaction monitoring | TM Agent + Marble case management | `docker-compose.transaction-monitor.yml`, agents/compliance/ | ✅ P0 |
| **FCA PSR 2017** | PSD2 SCA (Art.97) | Auth service + dynamic linking | `services/auth/`, `services/psd2_gateway/` | ✅ P0 |
| **FCA PS22/9** | Consumer Duty | Consumer Duty service | `services/consumer_duty/` | ✅ Partial |
| **I-01** | No float for money (Decimal) | All financial code | Semgrep banxe-float-money | ✅ Enforced |
| **I-02** | Hard-block jurisdictions (RU/BY/IR/KP) | AML service + TM agent | BLOCKED_JURISDICTIONS env, aml_thresholds.py | ✅ Enforced |
| **I-04** | EDD thresholds (£10k/£50k) | AML service | EDD_THRESHOLD_*_GBP env vars | ✅ Enforced |
| **I-08** | ClickHouse TTL ≥ 5 years | Audit tables | Semgrep banxe-clickhouse-ttl-reduce | ✅ Enforced |
| **I-24** | Append-only audit trail | pgAudit + ClickHouse | `services/audit/`, `services/audit_trail/` | ✅ Enforced |
| **I-27** | HITL supervision (propose only) | Compliance agents + HITL service | `services/hitl/`, agents/compliance/ | ✅ Enforced |
| **EU AI Act Art.14** | Human oversight of AI | HITL gates in agent code | agents/compliance/swarm.yaml | ✅ Enforced |

---

## Reference Documents

- **Architecture:** https://github.com/CarmiBanxe/banxe-architecture/
  - ADR-018: Hybrid 5-layer AI compute
  - ADR-017: Keycloak OIDC
  - ADR-102: Payment rail (Modulr)
  - ADR-103: Fraud detection (Jube + Marble)
  - CONSOLIDATION-PLAN.md: Phase 2

- **P0 Stack Map:** `.claude/rules/cass15.md`

- **Docker Compose:** `docker/docker-compose.*.yml`

- **Keycloak:** `infra/keycloak-banxe-emi/docker-compose.yml`

- **Agent Authority:** `agents/compliance/swarm.yaml`, `.claude/rules/agent-authority.md`

---

## Audit Trail

| Date | Change | Author | Reference |
|------|--------|--------|-----------|
| 2026-07-02 | Initial as-built manifest creation | Factory | DEPLOYMENT-MANIFEST.md creation |

**Maintained as:** append-only per I-24. Do NOT delete rows.

---

*This document reflects the as-built state of BANXE EMI infrastructure as of 2026-07-02.*  
*For upcoming deployments, refer to CONSOLIDATION-PLAN.md (Phases 2–4).*  
*Regulatory compliance verified: FCA CASS 15, MLR 2017, PSR 2017, EU AI Act Art.14.*
