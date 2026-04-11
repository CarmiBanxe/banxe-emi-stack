# Prompt 17 Part 2/3 — EMI Compliance Experiment Copilot

> **Feature**: Compliance Action Agent + Experiment Management System
> **Ticket**: IL-CEC-01 | **Branch**: refactor/claude-ai-scaffold
> **Depends on**: Prompt 17 Part 1 (Knowledge Service)
> **All tools**: Open-source or free tier (Git + FastAPI + YAML)

---

## Context

The Experiment Copilot is a Claude Code-powered action agent that:
1. Reads knowledge from the Compliance KB (Part 1)
2. Designs and tracks compliance experiments (AML rule changes, KYC thresholds)
3. Opens Git PRs / issues for approved changes
4. Monitors experiment metrics (hit-rate, SAR yield, false positives)
5. Provides audit-friendly explanations for every decision

## Architecture

```
+--------------------+     +-------------------+     +------------------+
| Experiment Designer |---->| Compliance KB     |---->| Change Proposer  |
| (Claude Code)       |     | (Part 1 MCP)      |     | (Git PR + Issue) |
+--------------------+     +-------------------+     +------------------+
        |                          |                          |
        v                          v                          v
+--------------------+     +-------------------+     +------------------+
| Experiment Store    |     | Metrics Tracker   |     | Audit Trail      |
| (YAML/Markdown)     |     | (ClickHouse)      |     | (append-only)    |
+--------------------+     +-------------------+     +------------------+
```

## Phase 1 — Experiment Data Model

### 1.1 Directory structure

```
services/experiment_copilot/
  __init__.py
  models/
    __init__.py
    experiment.py       # Experiment Pydantic models
    metrics.py          # AML metrics models
    proposal.py         # Change proposal models
  store/
    __init__.py
    experiment_store.py # YAML-based store in compliance-experiments/
    audit_trail.py      # Append-only audit log
  agents/
    __init__.py
    experiment_designer.py  # Designs new experiments from KB
    change_proposer.py      # Opens Git PRs/issues
    experiment_steward.py   # Approves/rejects experiments
    metrics_reporter.py     # Generates reports
  config.py

compliance-experiments/
  README.md
  draft/
  active/
  finished/
```

### 1.2 Experiment Model (`models/experiment.py`)

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional

class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"
    REJECTED = "rejected"

class ExperimentScope(str, Enum):
    TRANSACTION_MONITORING = "transaction_monitoring"
    KYC_ONBOARDING = "kyc_onboarding"
    CASE_MANAGEMENT = "case_management"
    SAR_FILING = "sar_filing"
    RISK_SCORING = "risk_scoring"

class ComplianceExperiment(BaseModel):
    id: str                          # e.g. "exp-2026-04-velocity-p2p"
    title: str
    scope: ExperimentScope
    status: ExperimentStatus
    hypothesis: str                  # What we expect to improve
    kb_citations: list[str]          # Citation IDs from KB
    created_at: datetime
    updated_at: datetime
    created_by: str                  # "claude-code" | "human"
    metrics_baseline: dict           # Before state
    metrics_target: dict             # Target state
    metrics_actual: dict = {}        # Actual results
    pr_url: str | None = None        # GitHub PR
    issue_url: str | None = None     # Issue tracker URL
    audit_entries: list[str] = []    # Audit trail IDs
    tags: list[str] = []

class ExperimentMetrics(BaseModel):
    hit_rate_24h: float | None = None      # Alert hit rate (target >60%)
    false_positive_rate: float | None = None  # False positives (target <30%)
    time_to_review_hours: float | None = None  # Review SLA
    amount_blocked_gbp: float | None = None
    sar_yield: float | None = None         # SAR conversion rate
    cases_reviewed: int = 0
    period_days: int = 0
```

### 1.3 AML Performance Baselines

Create `config/aml_baselines.yaml`:

```yaml
baselines:
  hit_rate_24h:
    current: 0.06        # 6% (92 alerts -> 6 SAR)
    target: 0.65         # 65% target
    sla_hours: 24
  review_sla:
    current_pct_meeting: 0.80  # 80% meet 48h SLA
    target_pct_meeting: 0.95   # 95% meet 24h SLA
  false_positive_rate:
    current: 0.94        # 94% are FPs
    target: 0.35         # Target <35%
  sar_yield:
    current: 0.065       # 6.5% of alerts become SARs
    target: 0.20         # 20% target

coverage_gaps:
  - scope: crypto_onramp
    status: not_covered
    priority: high
  - scope: merchant_risk
    status: partial
    priority: medium
  - scope: p2p_velocity
    status: not_covered
    priority: high
  - scope: cross_border_high_risk
    status: partial
    priority: high
```

## Phase 2 — Experiment Agents (4 agents)

### 2.1 Experiment Designer (`agents/experiment_designer.py`)

Responsibilities:
- Query KB for relevant regulation (e.g. "velocity limits for EMI")
- Identify coverage gaps from aml_baselines.yaml
- Generate experiment hypothesis with KB citations
- Create draft YAML file in `compliance-experiments/draft/`
- Include: scope, hypothesis, metrics_target, kb_citations

Input: `kb_query` (str), `scope` (ExperimentScope)
Output: `ComplianceExperiment` object + YAML file created

### 2.2 Change Proposer (`agents/change_proposer.py`)

Responsibilities:
- Convert approved experiment to Git PR
- Create branch: `compliance/exp-{experiment_id}`
- Update rule config files (e.g. `config/aml_rules.yaml`)
- Open GitHub PR with:
  - Experiment YAML as PR body
  - KB citations as references
  - Metrics baseline vs target table
  - Human-in-the-loop approval checklist
- Open issue in tracker with same data

Tools used:
- `subprocess` + `git` CLI
- GitHub REST API (via `httpx`)
- Template: `config/templates/compliance_pr_template.md`

### 2.3 Experiment Steward (`agents/experiment_steward.py`)

Responsibilities:
- Review draft experiments for completeness
- Check: hypothesis has KB citations, metrics have baselines
- Validate: no conflicts with active experiments
- Approve: move YAML to `active/`
- Reject: move to `rejected/` with reason
- Generate weekly summary report

### 2.4 Metrics Reporter (`agents/metrics_reporter.py`)

Responsibilities:
- Query ClickHouse for AML metrics
- Compare actual vs baseline vs target
- Generate markdown report per experiment
- Detect: improvement, regression, inconclusive
- Move finished experiments to `finished/`
- Export to Grafana dashboard via annotations

Metrics queries (ClickHouse SQL):
```sql
-- Hit rate query
SELECT
  count(*) as total_alerts,
  countIf(outcome = 'SAR') as sar_count,
  sar_count / total_alerts as hit_rate
FROM aml_alerts
WHERE created_at >= now() - INTERVAL 24 HOUR;
```

## Phase 3 — Experiment Store (YAML/Markdown)

### 3.1 Experiment Store (`store/experiment_store.py`)

- Save/load experiments as YAML files
- Organize by status: `compliance-experiments/{draft|active|finished}/`
- File naming: `{experiment_id}.yaml`
- Index file: `compliance-experiments/index.json` (auto-generated)
- Git-tracked: all changes committed automatically

### 3.2 Audit Trail (`store/audit_trail.py`)

- Append-only JSONL file: `data/audit/experiments.jsonl`
- Each entry: timestamp, actor, action, experiment_id, details
- Never delete entries
- Export to ClickHouse for analytics
- Retention: 7 years (FCA requirement)

### 3.3 PR Template (`config/templates/compliance_pr_template.md`)

```markdown
## Compliance Experiment: {title}

**Scope**: {scope} | **Created**: {created_at} | **Author**: {created_by}

### Hypothesis
{hypothesis}

### Knowledge Base Citations
{kb_citations_table}

### Metrics
| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Hit Rate | {baseline.hit_rate} | {target.hit_rate} | EBA GL §4.2 |
| False Positives | {baseline.fp_rate} | {target.fp_rate} | FATF Rec 10 |

### Human-in-the-Loop Checklist
- [ ] CTIO reviewed and approved
- [ ] Compliance officer sign-off
- [ ] Backtest results reviewed
- [ ] Rollback plan defined
```

## Phase 4 — MCP Tools (4 new tools)

Add to `banxe_mcp/tools/experiment_copilot.py`:

Tool 1: `experiment.design`
- Design new experiment from KB query
- Input: query, scope, created_by
- Output: experiment object + YAML path

Tool 2: `experiment.list`
- List experiments by status/scope/tags
- Output: paginated experiment list

Tool 3: `experiment.get_metrics`
- Get current AML metrics vs baselines
- Output: ExperimentMetrics + comparison

Tool 4: `experiment.propose_change`
- Propose change for approved experiment
- Creates Git branch + PR + issue
- Requires HITL approval flag

## Phase 5 — FastAPI Endpoints

```
POST /api/v1/experiments/design          # Design experiment
GET  /api/v1/experiments                  # List experiments
GET  /api/v1/experiments/{id}             # Get experiment
PATCH /api/v1/experiments/{id}/approve    # Approve (HITL)
PATCH /api/v1/experiments/{id}/reject     # Reject
GET  /api/v1/experiments/metrics/current  # Current AML metrics
POST /api/v1/experiments/{id}/propose     # Open PR/Issue
GET  /api/v1/experiments/{id}/audit       # Audit trail
```

## Phase 6 — Tests (45+ tests)

```
tests/test_experiment_copilot/
  test_experiment_models.py      # 6 tests - Pydantic validation
  test_experiment_store.py       # 8 tests - YAML read/write
  test_experiment_designer.py    # 7 tests - KB query + draft creation
  test_change_proposer.py        # 6 tests - Git + PR creation (mocked)
  test_experiment_steward.py     # 5 tests - Approve/reject workflow
  test_metrics_reporter.py       # 7 tests - ClickHouse queries (mocked)
  test_mcp_tools.py              # 6 tests - MCP tool contracts
```

### Key scenarios:
- Designer queries KB and creates valid experiment YAML
- Steward rejects experiment with no KB citations
- Proposer creates PR with correct template (mocked GitHub API)
- Metrics reporter detects improvement > 10% vs baseline
- Audit trail is append-only (cannot delete)
- HITL checklist prevents auto-approve

## Acceptance Criteria

- [ ] 4 experiment agents implemented
- [ ] YAML experiment store working (draft/active/finished)
- [ ] PR template generates audit-friendly output with KB citations
- [ ] 4 MCP tools registered
- [ ] 8 FastAPI endpoints operational
- [ ] HITL checklist on every PR
- [ ] Audit trail is append-only JSONL
- [ ] AML baselines configured in YAML
- [ ] 45+ tests passing
- [ ] `compliance-experiments/` directory initialized with README

## Execution Order

1. Create `compliance-experiments/` structure + README
2. Implement Pydantic models (experiment, metrics, proposal)
3. Build YAML experiment store
4. Implement audit trail (append-only JSONL)
5. Implement 4 agents (designer, proposer, steward, reporter)
6. Create aml_baselines.yaml + PR template
7. Register 4 MCP tools
8. Add FastAPI routes
9. Write tests
10. Integration test: designer -> steward -> proposer flow

---

*Ticket: IL-CEC-01 | Prompt: 17 Part 2/3*
*Next: Part 3 — Realtime Transaction Monitoring Agent*
