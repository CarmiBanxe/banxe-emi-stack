# Queen Agent Context — BANXE UI Sprint
# Ruflo Hive Mind | IL-ADDS-01 | 2026-04-11

## Sprint Goal

Implement BANXE AI-driven design system with 3 frontend modules:
1. Dashboard (KPI cards + transactions + AML feed)
2. AML Monitor (alert table + risk heatmap + case detail)
3. KYC Wizard (5-step onboarding wizard)

## Sprint Constraints

- **Deadline**: FCA CASS 15 P0 | 7 May 2026
- **Dark mode only**: all UI uses OKLCH dark backgrounds
- **Style-only changes**: preserve all existing API calls and business logic
- **No hardcoded hex**: use CSS custom properties from tokens.css only
- **WCAG AA**: all text must meet 4.5:1 contrast minimum

## Coordination Rules

### Agent Order (SPARC methodology)
1. **Design-Researcher** → reads DESIGN.md, extracts tokens, identifies gaps
2. **UI-Architect** → designs component interfaces, proposes CVA variants
3. **Dashboard-Dev + AML-Dev + KYC-Dev** → implement in parallel (Phase 3)
4. **UI-Tester** → writes tests after each module completes
5. **Design-QA** → final review, visual diff, compliance check

### Error Handling
- Stitch MCP error → fallback to DESIGN.md tokens
- Design-QA flags → route back to responsible coder with diff
- Token missing in tokens.css → Design-Researcher fills gap
- WCAG failure → block merge until fixed

### Handoff Protocol
Each agent delivers a handoff note with:
- Files created/modified
- Tests written
- Issues found
- Next agent's required input

## NEVER (hard constraints)

- Modify compliance/backend without explicit user confirmation (QRAA)
- Use `float` for monetary amounts
- Hardcode hex values in components
- Add pre-checked consent checkboxes
- De-emphasize the Reject button in any consent flow
- Reduce ClickHouse TTL below 5 years
- Log PII in plaintext

## Key File Paths

```
frontend/src/design-system/DESIGN.md     ← single source of truth
frontend/src/design-system/tokens.css    ← CSS custom properties
frontend/tailwind.config.ts              ← Tailwind theme
frontend/src/components/ui/              ← shared components
frontend/src/modules/                    ← feature modules
frontend/src/__tests__/                  ← test files
.claude/CLAUDE-UI.md                     ← Claude agent context
```

## Success Criteria

✅ All DESIGN.md tokens mapped in tokens.css
✅ WCAG AA contrast ratios pass for all text/background combos
✅ No hardcoded hex values in components
✅ Consent flows have equal-weight buttons
✅ All financial amounts use tabular-nums
✅ Dashboard renders with dark mode
✅ KYC wizard navigates all 5 steps
✅ 60+ tests green

---
*Created: 2026-04-11 | IL-ADDS-01*
