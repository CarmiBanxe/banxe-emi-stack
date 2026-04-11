"""
services/design_pipeline/agents — BANXE UI Agents
IL-D2C-01 | BANXE EMI AI Bank

Domain-specific agents that use DesignToCodeOrchestrator with
compliance-aware prompts for BANXE-specific UI generation.

Agents:
  ComplianceUIAgent   — KYC/AML form generation from schemas
  TransactionUIAgent  — Payment flow screens (PSD2 SCA)
  ReportUIAgent       — FIN060/SAR report layout generation
  OnboardingAgent     — Step-by-step KYC onboarding flows
"""
