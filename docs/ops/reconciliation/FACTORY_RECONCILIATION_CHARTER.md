# FACTORY RECONCILIATION CHARTER

## Reconciliation Charter

- Существуют два независимых репозитория: Banxe EMI Stack и Legion Private Engine.
- Оба репозитория сохраняются целиком; уничтожение, вытеснение или замещение одного другим запрещено.
- Конвергенция означает сближение архитектурного качества и возможностей, а не слияние в один кодовый артефакт.
- Любая работа начинается с backup-first: stash/tag/snapshot до любых изменений.
- Все изменения выполняются только в изолированных worktree/ветках; main напрямую не изменяется.
- Разрешены только ADD, ADAPT, WRAP, MIRROR, EXTRACT PATTERNS, PORT SAFE IDEAS.
- Запрещены destructive merge, overwrite, delete, reset --hard и force-push на main.
- Legion → Banxe: запрещён перенос Tor, onion-routing, privacy-only и compliance-breaking компонентов.
- Каждый перенос оформляется как отдельный proposal и отдельный SAFE-PORT PR.
- Любая реализация допускается только после read-only audit и явного operator approval.
- Оба репозитория должны улучшаться без деградации функциональности.
- Финальный критерий: оба репозитория стали лучше, ни один не исчез.

## Operational Gates

### Before Phase 1 (Read-only audit)
- Оба репозитория найдены и их пути подтверждены.
- На обоих репозиториях создан backup-tag `pre-reconcile/*`.
- Для обоих репозиториев сохранён snapshot (`git log --oneline -20` и `ls -la`).
- Подтверждено, где находятся runtime entrypoints, dependency manifests и test harnesses.
- Подтверждено, какой репозиторий регулируемый (Banxe), а какой приватный/экспериментальный (Legion).

### Before Phase 3 (Additive implementation)
- Для каждой идеи существует отдельный approved proposal.
- Подтверждено, что перенос является ADD/ADAPT/WRAP, а не DELETE/REPLACE.
- Проверено, что перенос не затрагивает запрещённые компоненты.
- Для реализации создан отдельный worktree и отдельная feature-ветка.
- Определены тесты и quality gates до внесения изменений.

### Before any merge
- Все тесты зелёные в целевом репозитории.
- Semgrep/quality gates пройдены.
- Для Banxe подтверждено, что compliance-инварианты не нарушены.
- PR содержит SAFE-PORT аннотацию и ссылку на proposal.
- Нет признаков destructive operations в reflog/истории.
- Оператор дал явное разрешение на merge.

## Artifact Layout

- Snapshots:
  - `docs/ops/reconciliation/snapshots/snapshot-<date>-<repo>.txt`
- Audit docs:
  - `docs/ops/reconciliation/audits/audit-<date>-<repo>.md`
  - `docs/ops/reconciliation/audits/compare-<date>-banxe-vs-legion.md`
- Proposals:
  - `docs/ops/reconciliation/proposals/<idea-id>-proposal.md`
- Safe-port tracking:
  - `docs/ops/reconciliation/safe-port-register.md`
  - `docs/ops/reconciliation/ports/<idea-id>-safe-port.md`

## PR Annotation Standard

### SAFE-PORT PR template

- PR Type: `[SAFE-PORT]`
- Source pattern: `<banxe|legion>`
- Target repo: `<banxe|legion>`
- Proposal: `docs/ops/reconciliation/proposals/<idea-id>-proposal.md`
- Change type: `<ADD|ADAPT|WRAP|MIRROR|EXTRACT PATTERNS|PORT SAFE IDEAS>`
- Forbidden-components check: `PASS/FAIL`
- Compliance impact (Banxe only): `NONE / REVIEWED / BLOCKED`
- Test evidence: `<commands/results>`
- Notes: `<short summary>`

## First Audit Target

Порядок первого аудита должен быть таким:

1. **Repo topology** — сначала понять структуру обоих репозиториев, границы модулей и точки входа.
2. **Dependency manifests** — затем определить стек, библиотеки, model/tool/runtime зависимости.
3. **Runtime entrypoints** — после этого выяснить, как каждый движок реально запускается и оркестрируется.
4. **Safety/compliance surfaces** — затем выделить зоны риска: guardrails, сетевые обходы, privacy/Tor, compliance logic.
5. **Test harnesses** — в конце определить, как проверять, что additive-изменения ничего не сломали.

Этот порядок минимизирует риск преждевременного переноса идей без понимания границ, зависимостей и ограничений.
