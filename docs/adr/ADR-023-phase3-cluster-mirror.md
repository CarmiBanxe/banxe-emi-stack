# ADR-023: Phase 3 Cluster ADRs — EMI Applicability Mirror

- **Status:** Accepted
- **Date:** 2026-05-03
- **Canonical sources:** `banxe-architecture/docs/adr/ADR-031..034` — при любом расхождении преобладают канонические ADR.
- **Scope:** banxe-emi-stack и все EMI-сервисы на кластере evo1/evo2/legion.

## Purpose

This document maps the four Phase 3 cluster ADRs (ADR-031..034) from `banxe-architecture`
to their specific applicability within `banxe-emi-stack`. It does not repeat the full
decision text; it states what each ADR **requires of this repo**.

---

## ADR-031 — AI Execution Policy: EMI applicability

**Canonical:** `banxe-architecture/docs/adr/ADR-031-ai-execution-policy.md`

### What this means for banxe-emi-stack

1. EMI services MUST NOT call any cloud LLM API directly (Anthropic, OpenAI, or any
   third-party). All inference routes via `legion:4000` (LiteLLM v2).
2. The following paths MUST NEVER be sent to any AI surface (local or cloud):
   `compliance/cases/*`, `kyc/raw/*`, `secrets/*`, `.env*`, `**/*.pem`, `**/id_*`.
3. Claude Code (cloud meta-plane) may read repo files for planning; it MUST NOT receive
   raw KYC documents, CAMT statement payloads, or unredacted audit logs in context.
4. Agents within this repo that call inference must route via `KBQueryPort` or a named
   LiteLLM alias — never via direct model ID or direct Ollama URL.

**Invariants bound:** INV-AI-01 (`INVARIANTS.md`), I-32 (`banxe-architecture/INVARIANTS.md`),
I-33 (`banxe-architecture/INVARIANTS.md`).

---

## ADR-032 — GLM-4.5-Air Distributed Inference: EMI applicability

**Canonical:** `banxe-architecture/docs/adr/ADR-032-glm45-air-distributed.md`
**Benchmark:** `banxe-architecture/benchmarks/glm-master-2026-05-03.md`

### What this means for banxe-emi-stack

1. When EMI agentic tasks (reconciliation analysis, compliance KB queries, FIN060 drafting)
   require a `large` reasoning call, use alias `glm-air` or `glm-4.5-air-distributed`
   via `legion:4000`. Do not hard-code `evo1:8081`.
2. Regression threshold: if generation drops below **~17 tok/s**, the agent MUST fall
   back gracefully (LiteLLM handles this per ADR-032 §Failover order) — no code change
   required in this repo.
3. The API key for `glm-master` lives in the evo1 systemd unit only. It MUST NOT appear
   in any file in this repo (INV-IAM-01, I-34).

---

## ADR-033 — ufw Perimeter Posture: EMI applicability

**Canonical:** `banxe-architecture/docs/adr/ADR-033-ufw-perimeter.md`

### What this means for banxe-emi-stack

1. All EMI stack workloads are hosted on the evo1/evo2/legion cluster. The ufw posture
   in ADR-033 applies to those hosts — this repo does not configure ufw, but must not
   assume port accessibility beyond what ADR-033 allows.
2. Services that open new inbound ports (e.g. a new FastAPI microservice) must first add
   the port to ADR-033 (via amendment or new ADR) before deploying.
3. Forbidden: any service in this repo binding to `0.0.0.0` on a port not listed in
   ADR-033's host matrix. Use `127.0.0.1` or the LAN-scoped bind address.

---

## ADR-034 — Aider/Continue Routes: EMI applicability

**Canonical:** `banxe-architecture/docs/adr/ADR-034-aider-routes.md`

### What this means for banxe-emi-stack

1. Developer tooling (Aider, Continue) used in this repo MUST resolve to one of:
   `ai`, `ai-heavy`, `reasoning`. Direct model IDs in IDE config are a P2 lint failure.
2. **`reasoning` alias is PENDING_PASS** (P3.2 not yet closed). Until P3.2 PASS is
   recorded in `banxe-architecture/docs/ROADMAP-MATRIX.md §AI Plane — Alias status`,
   the `reasoning` alias MUST NOT be used in any production compliance flow
   (AML screening, KYC, SAR filing, FIN060 generation). Planning tasks only.
3. `ai` is the default day-to-day route for Aider in this repo.

**Related warning:** `docs/AI-PLUMBING.md` (reasoning PENDING_PASS warning block, if
present); `banxe-architecture/docs/ROADMAP-MATRIX.md §reasoning alias status`.

---

## Related canonical artefacts

- ADR-031: `banxe-architecture/docs/adr/ADR-031-ai-execution-policy.md`
- ADR-032: `banxe-architecture/docs/adr/ADR-032-glm45-air-distributed.md`
- ADR-033: `banxe-architecture/docs/adr/ADR-033-ufw-perimeter.md`
- ADR-034: `banxe-architecture/docs/adr/ADR-034-aider-routes.md`
- Benchmark: `banxe-architecture/benchmarks/glm-master-2026-05-03.md`
- Phase 3 Cluster Snapshot: `banxe-architecture/docs/ROADMAP-MATRIX.md §Phase 3 Cluster Snapshot`

## Local invariants

- INV-AI-01 (this repo `INVARIANTS.md`): no direct cloud LLM calls from EMI services.
- INV-IAM-01 (this repo `INVARIANTS.md`): no direct credentials in configs.

## Compliance mapping

- FCA CASS 15 (deadline 2026-05-07) — ADR-031 deny-paths protect client fund data.
- GDPR Art. 9 — biometric/KYC data must not leave the on-prem perimeter.
- FCA SYSC 8 (outsourcing) — cloud AI routes treated as material outsourcing; restricted.
