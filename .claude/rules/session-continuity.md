# Session Continuity Protocol — BANXE AI BANK
# Source: .claude/CLAUDE.md (SESSION CONTINUITY PROTOCOL section)
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Ensure no context is lost between Claude Code sessions

## After Every Task Completion

1. Check for pending work:
   ```bash
   grep -c "pending\|⏳\|IN_PROGRESS" /home/mmber/banxe-architecture/INSTRUCTION-LEDGER.md
   ```
2. Remind CEO about unfinished plan (table format from banxe-architecture/CLAUDE.md)
3. Response handling:
   - "да" / "yes" → continue without questions
   - "нет" / "позже" → wait
   - Other task → execute → remind again after

## New Session Start — First Message Template

```
🔄 Восстановление контекста...
Последний IL: IL-0XX | Тесты: NNN/NNN | Keycloak: :8180 ✅
📋 Незавершённый план: N задач (P0 дедлайн: 7 мая — safeguarding)
Продолжить с Задачи N или есть другие приоритеты?
```

## Invariant

Violating session continuity = P1 defect. The protocol is non-optional.

## References

- Full protocol: `.claude/CLAUDE.md`
- Instruction Ledger: `banxe-architecture/INSTRUCTION-LEDGER.md`
- Architecture repo: `https://github.com/CarmiBanxe/banxe-architecture`
