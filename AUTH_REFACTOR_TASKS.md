# Auth Refactor Tasks

## Phase A — inventory
- [ ] Mark every inline JWT encode/decode location in api/routers/auth.py
- [ ] Mark every login/refresh endpoint branch
- [ ] Identify which code belongs to transport vs auth domain service
- [ ] Identify existing token_manager methods reusable without import from BANXE.RAR
- [ ] Identify IAM operations already representable via services/iam/iam_port.py

## Phase B — extraction
- [ ] Introduce auth application service/use-case layer
- [ ] Move token issuance/refresh to token manager boundary
- [ ] Keep router limited to request/response mapping
- [ ] Route IAM operations only through IAMPort-compatible dependency
- [ ] Preserve current response schema and tests

## Phase C — import readiness
- [ ] Define adapter seam for BANXE.RAR auth token logic
- [ ] Define adapter seam for BANXE.RAR IAM logic
- [ ] Decide selective import points for SCA and 2FA
- [ ] Reject direct import into api/routers/auth.py
