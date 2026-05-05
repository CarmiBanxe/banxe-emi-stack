# ADR-022: Keycloak IAM Cutover (mirror of ADR-017)

- **Status:** Accepted
- **Date:** 2026-05-03
- **Canonical source:** `banxe-architecture/decisions/ADR-017-keycloak-iam-cutover.md` — в случае любого расхождения преобладает ADR-017.
- **Scope:** banxe-emi-stack, banxe-compliance-api, banxe-dashboard, deep-search, drive_watcher, все будущие EMI-сервисы.

## Decision (mirror of ADR-017 §1–§7)
1. Единый IAM-plane: Keycloak realm `banxe-emi` на evo1:8180 — единственный санкционированный issuer токенов для EMI-сервисов.
2. Service-to-service auth через client_id + client_secret в realm `banxe-emi`; короткоживущие OIDC-токены (≤ 15 минут).
3. OIDC discovery: `http://evo1:8180/realms/banxe-emi/.well-known/openid-configuration`. Hardcoded endpoints запрещены.
4. Mappers: `service_id`, `environment`, `compliance_scope`. Audit log retention ≥ 12 месяцев (FCA CASS 15).
5. Rotation policy: client_secrets раз в 90 дней или по инциденту. Master key — operator-supplied env, не коммитится.
6. Backout: до подтверждённого PASS на evo1 — Legion local IAM (`--user` units) включаемый по runbook `docs/Keycloak-next-session-roadmap.md §IAM cutover plan v0.1`. После PASS — Legion local IAM удерживается 7 дней, затем декомиссионируется.
7. Энфорсмент: pre-commit hook + review checklist в каждом EMI-репо. Нарушение PII/IAM routing = P0 incident.

## Related canonical artefacts
- ADR-017 (canonical): `banxe-architecture/decisions/ADR-017-keycloak-iam-cutover.md`
- INVARIANTS canonical: I-34, I-35 (`banxe-architecture/INVARIANTS.md`)
- GAP-REGISTER canonical: G-IAM-01..G-IAM-08 (`banxe-architecture/GAP-REGISTER.md`)
- ROADMAP-MATRIX P3.4: `banxe-architecture/docs/ROADMAP-MATRIX.md §Phase 3 — Delivery Phases (P3.x)`

## Local invariants reflected
- INV-IAM-01 (this repo INVARIANTS.md): no direct credentials in EMI configs.
- INV-IAM-02 (this repo INVARIANTS.md): Keycloak realm `banxe-emi` as single IAM issuer.

## Compliance mapping
- FCA CASS 15 (deadline 2026-05-07).
- FCA MLR 2017 (audit trail).
- GDPR Art. 32 (security of processing).
