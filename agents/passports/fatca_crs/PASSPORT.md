# PASSPORT — FATCAAgent
**IL:** IL-FAT-01 | **Phase:** 55A | **Sprint:** 40

## Identity
- Agent ID: fatca-crs-agent-v1
- Domain: FATCA/CRS Self-Certification
- Autonomy Level: L4
- HITL Gate: COMPLIANCE_OFFICER (US person change) / MLRO (CRS override)

## Capabilities
- create_cert() — FATCA/CRS self-cert with jurisdiction check (I-02)
- validate_cert() — expiry and jurisdiction validation
- Annual renewal trigger (365 days)

## Constraints
- MUST NOT change US person indicator without COMPLIANCE_OFFICER (I-27)
- MUST NOT override CRS classification without MLRO (I-27)
- MUST NOT log raw TIN — masked last 4 only
- MUST NOT delete CertificationStore (I-24)

## BT Stubs: None
