# Pull Request

## Summary
_What does this PR do? One paragraph._

## Why
_Why is this change needed? Link to ticket or regulatory requirement._

Ticket: <!-- IL-XX-NN or GitHub issue # -->

---

## Domains Checklist

Check all domains this PR touches:

- [ ] Backend Python (`services/`)
- [ ] API contracts (`api/`)
- [ ] AML / KYC (`services/aml/`, `services/kyc/`)
- [ ] Ledger (`services/ledger/`)
- [ ] Reporting / FIN060 (`services/reporting/`, `dbt/`)
- [ ] Security / auth (`services/auth/`, `services/iam/`)
- [ ] Database migrations (`infra/`)
- [ ] Documentation (`docs/`)

---

## Risks
_What could go wrong? Any backward-compatibility, data, or compliance risks?_

## Tests

- [ ] Unit tests added / updated
- [ ] Integration tests added / updated
- [ ] Negative cases covered
- [ ] `pytest tests/ -x -q` passes locally

## Docs Updated

- [ ] `docs/API.md` (if API changed)
- [ ] `docs/architecture/` (if component changed)
- [ ] `docs/compliance/` (if control changed)
- [ ] `docs/runbooks/` (if operational procedure changed)
- [ ] ADR added (if architectural decision made)
- [ ] N/A — docs not required for this change

## Rollout / Rollback

- **Rollout**: <!-- feature flag? staged? coordinated with migration? -->
- **Rollback**: <!-- how to undo if this causes problems -->
- [ ] Rollback tested

---

## Reviewer Focus
_What should reviewers pay most attention to?_

<!-- e.g., "Please review the Decimal rounding logic in services/recon/reconciliation_engine.py" -->
