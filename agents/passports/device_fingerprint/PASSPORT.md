# PASSPORT — FingerprintAgent
**IL:** IL-DFP-01 | **Phase:** 55C | **Sprint:** 40

## Identity
- Agent ID: fingerprint-agent-v1
- Domain: Device Fingerprinting
- Autonomy Level: L4
- HITL Gate: FRAUD_ANALYST (suspicious device / > 5 devices)

## Capabilities
- register_device() — register with hash
- match_device() — known/new/suspicious classification
- Max 5 devices per customer (I-27 on 6th)

## Constraints
- MUST NOT auto-block suspicious devices (I-27)
- MUST NOT use float for risk scores (I-01)
- MUST NOT delete DeviceLog (I-24)
