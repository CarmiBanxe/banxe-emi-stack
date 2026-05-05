# ADR-021: AI Plane and PII/AML Routing for EMI Stack

- **Status:** Accepted
- **Date:** 2026-05-03
- **Deciders:** Architecture WG (Banxe)
- **Scope:** banxe-emi-stack, banxe-compliance-api, banxe-dashboard,
  deep-search, drive_watcher, future EMI services
- **Supersedes:** —
- **Related:** ROADMAP Phase 3 sync (banxe-emi-stack@cbaf57c),
  AI-PLUMBING.md (banxe-emi-stack@fe26fcb), INVARIANTS.md (PII/AML),
  GAP-REGISTER (G-AI-*, G-PII-*)

## Context

EMI стек выходит на исполнение FCA CASS 15 (deadline 2026-05-07) и
требует единого, аудируемого AI-канала для compliance/API/dashboard.
Текущее состояние:

- Несколько сервисов исторически дергали Claude/Gemini/Groq/OpenAI
  напрямую, что несовместимо с PII/AML обязательствами EMI и FCA.
- Развёрнут локальный LiteLLM v2 router на `http://legion:4000/v1`
  с алиасами `ai`, `ai-heavy`, `glm-air`, `reasoning`,
  `banxe-general`, `fast`, `coding`.
- Идёт миграция сервисов с Legion WSL2 на evo1 `/data/banxe/`,
  Legion `--user` units сохраняются как rollback до PASS.

Без единого архитектурного решения нарушения PII guardrails будут
повторяться от репо к репо.

## Decision

1. **Единый AI-plane.** LiteLLM v2 router (`http://legion:4000/v1`,
   в перспективе — evo1) — единственный санкционированный entrypoint
   для AI-вызовов из любого EMI-сервиса. Прямые вызовы внешних LLM
   из сервисного кода запрещены.

2. **Алиасы как контракт.** Сервисы обращаются только по алиасам
   (`ai`, `ai-heavy`, `glm-air`, `reasoning`, `banxe-general`,
   `fast`, `coding`). Backing-модели — деталь реализации plane,
   не сервиса.

3. **PII/AML guardrails — binding.** Контент по путям:
   `compliance/cases/*`, `kyc/raw/*`, `secrets/*`, `.env*`,
   `**/*.pem`, `**/id_*` — обрабатывается ТОЛЬКО локальными
   алиасами (`ai`, `ai-heavy`, `glm-air`, `reasoning`).
   Источник правды политики: `banxe-infra/ai-routing/policy.yaml`.

4. **Секреты.** `LITELLM_MASTER_KEY` поставляется оператором через
   env, никогда не коммитится. Ротация — стандартная процедура
   secrets-mgmt (см. ADR по secrets, если есть).

5. **Миграция как шаблон.** Перенос сервисов Legion WSL2 → evo1
   `/data/banxe/` выполняется по схеме «двойной запас»:
   старые `--user` units на Legion остаются включаемыми до
   подтверждённого PASS на evo1.

6. **Энфорсмент.**
   - pre-commit hook + code review checklist в каждом EMI-репо.
   - Нарушение PII/AML routing = **P0 security incident**
     (архитектурный инвариант, не локальная политика репо).

## Consequences

**Положительные**
- Единая точка аудита AI-трафика для FCA/compliance.
- Возможность смены backing-моделей без рефакторинга сервисов.
- PII/AML guardrails становятся проверяемыми централизованно.

**Отрицательные / риски**
- Точка отказа: LiteLLM router. Митигация — health-checks,
  План Б на evo1, документированный rollback на Legion.
- Алиас `reasoning` (qwen3:235b-a22b) — статус pending PASS;
  до PASS не использовать в проде compliance-флоу.

## Compliance mapping

- FCA CASS 15 (исполнение к 2026-05-07): требование контроля
  обработки клиентских данных — закрывается guardrails (п.3).
- GDPR Art. 5/32: minimisation + security — закрывается локальной
  обработкой PII через on-prem алиасы.

## Enforcement artefacts

- `banxe-infra/ai-routing/policy.yaml` (deny-paths, alias map).
- pre-commit hook: запрет прямых вызовов внешних LLM SDK в
  EMI-сервисах.
- Review checklist: пункт «AI calls go via LiteLLM aliases only».
- INVARIANTS.md: добавить инвариант `INV-AI-01: no direct cloud
  LLM calls from EMI services` и `INV-PII-01: deny-paths routing`.

## Rollout

- T+0 (этот ADR Accepted): фиксация в `banxe-architecture`.
- T+1: PR в `banxe-emi-stack` со ссылкой на ADR-021 в
  `ROADMAP.md` Phase 3 sync и `docs/AI-PLUMBING.md`.
- T+2: добавить INV-AI-01 / INV-PII-01 в `INVARIANTS.md`.
- T+3: закрыть соответствующие записи в `GAP-REGISTER.md`.
