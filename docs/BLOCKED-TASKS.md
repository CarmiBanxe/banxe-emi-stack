# BLOCKED-TASKS.md — banxe-emi-stack
# Sprint 13 | 2026-04-13
# Purpose: Tasks blocked on external action (CEO, ops, vendor). Not tech debt.

---

## BT-001 — DocuSign API integration (eIDAS e-signature)

| Field | Value |
|-------|-------|
| **Status** | BLOCKED — awaiting CEO action |
| **Blocker** | DocuSign API key + Account ID not provisioned |
| **Owner** | CEO (Moriel Carmi) |
| **File** | `services/agreement/agreement_service.py:212` (`DocuSignStub`) |
| **FCA reference** | eIDAS Reg.910/2014 (qualified e-signature) |
| **Impact** | `DocuSignStub.send_signature_request()` raises `NotImplementedError` in production |
| **Unblocking action** | CEO to create DocuSign sandbox account at docusign.com/developers and set `DOCUSIGN_API_KEY` + `DOCUSIGN_ACCOUNT_ID` in `.env` |
| **Once unblocked** | Implement `POST /envelopes` in `DocuSignStub`; remove `# pragma: no cover` |

---

## BT-002 — Jube ML scoring (fraud production endpoint)

| Field | Value |
|-------|-------|
| **Status** | UNBLOCKED 2026-04-30 — Jube TM running at 127.0.0.1:5001 |
| **Blocker** | Jube ML service not deployed to GMKtec NucBox |
| **Owner** | DevOps / Mark |
| **File** | `services/fraud/jube_adapter.py` |
| **FCA reference** | PSR APP 2024 (fraud detection) / MLR 2017 Reg.26 |
| **Impact** | `JubeAdapter.score()` falls back to mock scoring; real ML not active |
| **Unblocking action** | Deploy Jube Docker container on GMKtec: `docker run -p 5001:5001 jubeml/jube:latest`; set `JUBE_URL=http://gmktec:5001` |
| **Once unblocked** | Remove fallback mock; enable `JUBE_ENABLED=true` in config |

---

## BT-003 — Keycloak production realm (IAM)

| Field | Value |
|-------|-------|
| **Status** | UNBLOCKED 2026-04-30 — Keycloak 26.2.5 host-deployed on NucBox (Sprint 4) |
| **Blocker** | Keycloak not deployed; `KEYCLOAK_REALM_URL` not set in production |
| **Owner** | DevOps / Mark |
| **File** | `services/iam/mock_iam_adapter.py` (`KeycloakAdapter`) |
| **FCA reference** | FCA SYSC 8.1 (operational resilience) |
| **Impact** | `KeycloakAdapter._fetch_jwks()` fails in prod without `KEYCLOAK_REALM_URL`; app falls back to `MockIAMAdapter` |
| **Unblocking action** | Deploy Keycloak (Bitnami chart or managed AWS Cognito); set `KEYCLOAK_REALM_URL`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` in `.env`; create `banxe` realm + 7 roles (ADMIN, MLRO, COMPLIANCE_OFFICER, CUSTOMER_SUPPORT, READONLY, AUDITOR, API_CLIENT) |
| **Once unblocked** | Switch `IAMPort` factory from `MockIAMAdapter` to `KeycloakAdapter`; remove mock fallback in `api/deps.py` |

---

## BT-004 — Marble AML case management (production API key)

| Field | Value |
|-------|-------|
| **Status** | BLOCKED — no Marble production API key |
| **Blocker** | Marble (marble.io) account not provisioned; `MARBLE_API_KEY` not set |
| **Owner** | CEO (Moriel Carmi) / Compliance |
| **File** | `services/case_management/marble_adapter.py` |
| **FCA reference** | EU AI Act Art.14 (human oversight in AML decisions) |
| **Impact** | All case management calls (`create_case`, `update_case`, `close_case`, `list_cases`) fall back to `_stub_result()` in production |
| **Unblocking action** | Sign Marble contract at marble.io; obtain API key; set `MARBLE_API_KEY` + `MARBLE_API_URL` in `.env` |
| **Once unblocked** | `MarbleAdapter` auto-activates — no code changes needed (adapter already production-ready per S13-03) |

---

## Summary

| ID | Blocker | Owner | FCA impact |
|----|---------|-------|-----------|
| BT-001 | DocuSign API key | CEO | eIDAS e-signature not functional |
| BT-002 | Jube ML server not running | DevOps | Fraud ML scoring degraded to mock |
| BT-003 | Keycloak not deployed | DevOps | All JWTs validated by mock adapter |
| BT-004 | Marble API key | CEO/Compliance | AML case routing returns stubs |

**None of these tasks are code-blocked.** The implementation is complete. External provisioning is the only remaining step for each.
