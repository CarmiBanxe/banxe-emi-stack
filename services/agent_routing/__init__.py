"""
services/agent_routing — Agent Routing Layer (ARL)
IL-ARL-01 | banxe-emi-stack

Three-tier routing for LLM compliance tasks:
  Tier 1: Rule engine / BM25 (~$0 per decision)
  Tier 2: Mid-tier LLM (Haiku-class)
  Tier 3: Top model (Opus-class) / Swarm

Target: ~60-70% token cost reduction for routine operations.
"""
