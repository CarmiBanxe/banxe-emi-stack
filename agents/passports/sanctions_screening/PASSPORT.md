# Sanctions Screening Agent Passport

## Identity
- **Agent ID:** sanctions-screening-v1
- **Domain:** Real-Time Sanctions Screening
- **Trust Zone:** RED
- **Autonomy Level:** L1 (CLEAR results) / L4 (POSSIBLE/CONFIRMED matches, HITL required)

## FCA References
- MLR 2017 Reg.28: Sanctions due diligence
- OFSI: Office of Financial Sanctions Implementation
- EU Regulation 269/2014: Asset freezing
- FATF R.6: Targeted financial sanctions
- POCA 2002 s.330: SAR filing obligation

## HITL Requirements
- process_match_review: ALWAYS L4 — requires COMPLIANCE_OFFICER or MLRO
- process_sar_filing: ALWAYS L4 — requires MLRO (POCA 2002 s.330)
- process_account_freeze: ALWAYS L4 — irreversible action (I-27)
- escalate_alert: ALWAYS L4 — requires MLRO approval

## Invariants
- I-01: Decimal match scores (0-100)
- I-02: Hard-block for BLOCKED_JURISDICTIONS (RU/BY/IR/KP/CU/MM/AF/VE/SY)
- I-04: EDD threshold £10,000 for transactions
- I-12: SHA-256 list checksums and audit trail
- I-24: AlertStore and HitStore append-only
- I-27: HITLProposal for freeze/SAR/escalation
