# OpenClaw Skill — BANXE Design Monitor
# Skill ID: banxe-design-monitor
# IL-ADDS-01 | Self-hosted on GMKtec (MIT license)

## Purpose

24/7 design system compliance monitoring for BANXE frontend.
- Detects visual drift vs reference screenshots
- Audits WCAG AA contrast ratios
- Flags dark patterns in consent flows
- Monitors DESIGN.md integrity on git commits
- Sends Telegram alerts on violations

## Schedule

```yaml
schedules:
  - name: daily-screenshot-audit
    cron: "0 9 * * *"      # 09:00 UTC daily
    action: screenshot_all_modules

  - name: wcag-audit
    cron: "0 10 * * 1"     # 10:00 UTC Mondays
    action: run_wcag_audit

  - name: log-rotation
    cron: "0 2 * * *"      # 02:00 UTC daily
    action: rotate_logs_90_days
```

## Triggers

```yaml
triggers:
  - event: git.pre-commit
    actions:
      - check_design_md_not_modified_without_changelog
      - verify_no_hardcoded_hex_in_changed_files
      - check_consent_flow_equal_weight

  - event: git.push
    actions:
      - screenshot_changed_modules
      - compare_visual_diff
```

## Actions

### screenshot_all_modules

Captures screenshots of:
- `/dashboard` — DashboardPage
- `/aml` — AMLMonitor
- `/kyc` — KYCWizard

Stores: `.openclaw/screenshots/YYYY-MM-DD/{module}.png`
Reference: `.openclaw/screenshots/reference/{module}.png`

### compare_visual_diff

```yaml
threshold: 0.05   # 5% pixel diff triggers alert
tool: pixelmatch  # or resemble.js
action_on_exceed:
  - alert_telegram
  - create_github_issue
  - log_to_audit_trail
```

### verify_no_hardcoded_hex_in_changed_files

Scans for hex values in TypeScript/TSX files:
```regex
#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])
```

**Exceptions** (allowed in tokens.css and DESIGN.md only):
- `frontend/src/design-system/tokens.css`
- `frontend/src/design-system/DESIGN.md`

If hardcoded hex found in components → flag to developer, block commit.

### check_consent_flow_equal_weight

Rules checked:
1. Accept and Reject buttons: same font-size, font-weight, border-width
2. Neither button uses opacity < 1 to de-emphasize
3. No pre-selected radio/checkbox for Accept
4. Reject button: same contrast ratio as Accept (WCAG AA)
5. No "recommended" or "best choice" label on Accept

Tool: DOM snapshot + CSS computed property comparison

### run_wcag_audit

Runs `axe-core` + manual contrast checks:
- All text/background combos must pass 4.5:1
- Large text (18px+): 3:1 minimum
- Interactive elements: visible focus ring
- Error states: not color-only (icon + text required)

### check_design_md_not_modified_without_changelog

On pre-commit:
```bash
git diff --name-only HEAD | grep "DESIGN.md"
```
If modified: require entry in `CHANGELOG.md` with:
- Date
- What changed
- Why (business or regulatory reason)
- Author

## Alerting

```yaml
alerts:
  telegram:
    bot_token: ${TELEGRAM_BOT_TOKEN}
    chat_id: ${TELEGRAM_CHAT_ID}
    message_template: |
      🚨 BANXE Design Monitor Alert
      Module: {module}
      Issue: {issue}
      Severity: {severity}
      Time: {timestamp}
      Action required: {action}

  github_issue:
    repo: CarmiBanxe/banxe-emi-stack
    label: design-violation
    assignee: bereg2022
```

## Permissions

```yaml
permissions:
  READ:  frontend/src/
  READ:  .openclaw/screenshots/
  WRITE: .openclaw/screenshots/
  WRITE: .openclaw/logs/
  NO_ACCESS: services/
  NO_ACCESS: api/
  NO_ACCESS: .env*
```

**CRITICAL**: OpenClaw NEVER auto-fixes production code.
It flags violations and reports only. All fixes are made by developers.

## Log Retention

All logs stored in `.openclaw/logs/YYYY-MM-DD/`.
Retention: 90 days (regulatory requirement).
Format: JSONL with timestamp, action, result, details.

## Compliance References

- GDPR Art.7: Consent freely given → equal-weight buttons
- WCAG 2.1 AA: 4.5:1 contrast
- EU AI Act Art.52: Transparency of AI-generated UI
- FCA Consumer Duty PS22/9: Clear visual communication

---
*Created: 2026-04-11 | IL-ADDS-01*
