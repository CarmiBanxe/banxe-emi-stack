# Security Policy — BANXE AI BANK
# Source: .semgrep/banxe-rules.yml, CLAUDE.md Hard Constraints
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Security rules enforced across all code

## Secrets Management

- NEVER hardcode secrets, tokens, API keys, or passwords in source code
- All secrets via `.env` files or `/etc/banxe/secrets.env`
- `.env` is in `.gitignore` — never committed
- Template: `.env.example` (contains structure, never real values)

## Code Security Rules (Semgrep-enforced)

| Rule ID | Severity | What it catches |
|---------|----------|-----------------|
| `banxe-hardcoded-secret` | ERROR | Hardcoded tokens/passwords |
| `banxe-sql-injection-python` | ERROR | f-string SQL queries (Python) |
| `banxe-sql-injection-javascript` | ERROR | Template literal SQL queries (JS) |
| `banxe-unsafe-eval` | ERROR | `eval()` usage |
| `banxe-float-money` | ERROR | `float` used for monetary values |
| `banxe-log-pii` | WARNING | Logging PII data |
| `banxe-no-plain-password` | ERROR | Plaintext password storage |
| `banxe-shell-injection` | ERROR | Unsanitized shell commands |
| `banxe-audit-delete` | ERROR | DELETE on audit tables (I-24) |
| `banxe-clickhouse-ttl-reduce` | ERROR | TTL reduction below 5yr (I-08) |

## Sanctioned Jurisdictions

Technologies, services, or data flows involving these jurisdictions are BLOCKED:
Russia (RU), Belarus (BY), Iran (IR), North Korea (KP), Cuba (CU),
Myanmar (MM), Afghanistan (AF), Venezuela (VE), Syria (SY)

## References

- Semgrep rules: `.semgrep/banxe-rules.yml`
- Environment template: `.env.example`
