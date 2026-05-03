# Contributing to banxe-emi-stack

This document covers the rules every contributor must follow before opening a PR.

---

## Quality gate

Every PR must pass all pre-commit hooks and CI gates before merge.
Run the full gate locally:

```bash
bash scripts/quality-gate.sh
```

Or per-gate:

```bash
ruff check .                                          # lint
ruff format --check .                                 # format
semgrep --config .semgrep/banxe-rules.yml --error     # security rules
semgrep --config .semgrep/banxe-rules/iam-no-direct-creds.yml --error  # IAM guard
python -m pytest tests/ -x -q --no-cov               # fast tests
```

---

## IAM Credentials Guard (INV-IAM-01)

**You must not commit direct credentials in any config file.**

This is enforced by:

1. **Pre-commit hook** `iam-no-direct-creds` — runs on every `git commit`. Blocks if
   a literal password, `client_secret`, `api_key`, `auth_token`, `access_token`, or
   `private_key` value is found in any `.yaml`, `.yml`, or `.json` file outside of
   `.semgrep/` and `tests/`.

2. **Semgrep rule** `.semgrep/banxe-rules/iam-no-direct-creds.yml` — runs in CI
   (Semgrep gate) and in the `semgrep-banxe` pre-commit hook. Same logic, more precise
   pattern matching.

3. **Gitleaks** — runs as the first CI gate on every push. Catches secret patterns in
   the git history (not just staged files).

### What is a "direct credential"?

```yaml
# BLOCKED — literal value that is not a template placeholder
db_password: "MySuperSecret123"
client_secret: "abc123def456"
api_key: "sk-live-..."
```

```yaml
# ALLOWED — environment variable reference, placeholder, or empty
db_password: "${DB_PASSWORD}"
client_secret: "<CHANGEME>"
api_key: ""
```

### Why this rule exists

- **INV-IAM-01** (`INVARIANTS.md`): EMI services must not store static credentials.
  All secrets are issued by Keycloak realm `banxe-emi` or supplied via operator-managed
  env (never committed).
- **ADR-022** (`docs/adr/ADR-022-keycloak-iam-cutover.md`) §7 (enforcement).
- **FCA CASS 15 + GDPR Art. 32** — a committed credential is a reportable data breach.
- **I-34** (canonical: `banxe-architecture/INVARIANTS.md`).

**Violation severity: P0 — security incident.**

### If the hook fires incorrectly (false positive)

1. Check that the value is actually a placeholder (e.g. `${MY_VAR}`).
2. If it's a test fixture value that does not resemble a real secret, add the file to
   `.semgrep/banxe-rules/iam-no-direct-creds.yml` `paths.exclude` and document why.
3. Never use `--no-verify` to bypass this hook without CTIO sign-off.

---

## Financial invariants

All money amounts must use `Decimal` — never `float`. See `INVARIANTS.md §I-01`.

## Audit trail

Every state-mutating operation must write to ClickHouse or pgAudit. Never delete audit
records (`INVARIANTS.md §I-24`).

## Branch naming

```
feat/<scope>-<description>
fix/<scope>-<description>
refactor/<description>
docs/<description>
hotfix/<description>
```

## Commit format

```
<type>(<scope>): <description> [IL-NNN]
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.

---

## References

- Financial invariants: `INVARIANTS.md`
- Gap register: `GAP-REGISTER.md`
- Pre-commit config: `.pre-commit-config.yaml`
- Semgrep rules: `.semgrep/banxe-rules.yml`, `.semgrep/banxe-rules/iam-no-direct-creds.yml`
- IAM ADR: `docs/adr/ADR-022-keycloak-iam-cutover.md`
