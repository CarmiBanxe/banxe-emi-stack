"""
services/design_pipeline — Design-to-Code Pipeline
IL-D2C-01 | BANXE EMI AI Bank

Open-source design-to-code automation using Penpot MCP + Style Dictionary +
Mitosis + AI Orchestration (FastAPI + LangChain + Ollama).

Architecture:
  Penpot (self-hosted) → PenpotMCPClient → TokenExtractor → StyleDictionary
                      → DesignToCodeOrchestrator → CodeGenerator (Mitosis)
                      → VisualQAAgent → BANXE component library

FCA references:
  - GDPR Art.25: Privacy-by-Design in generated UI forms
  - PSD2 SCA: Transaction authentication UI requirements
  - Consumer Duty PS22/9: Clear, fair UI communication
  - EU AI Act Art.52: Transparency in AI-generated content
"""

__version__ = "0.1.0"
