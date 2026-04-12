# AI Agent Rules — BANXE AI BANK
# Rule ID: 80-ai-agents | Load order: 80
# Created: 2026-04-12 (IL-RETRO-02) | IL-ARL-01, IL-SK-01, IL-069..071

## Agent Types

| Type | Location | Purpose |
|------|----------|---------|
| Compliance swarm agents | `agents/compliance/` | AML, KYC, sanctions, TM, CDD, fraud |
| Operational agents | `.claude/agents/*.md` | Recon, reporting, safeguarding |
| Skill agents | `agents/compliance/skills/` | Recon analysis, breach prediction |
| MCP-interfaced services | `banxe_mcp/server.py` | Claude-callable tools |

## Soul File Structure

Every new AI skill requires a `.soul.md` file at `agents/compliance/soul/<agent-name>.soul.md`:

```markdown
# <AgentName> Soul — BANXE AI BANK
## Identity
## Capabilities
## Constraints (MUST NOT / MUST NEVER)
## Autonomy Level (L1-L4, see agent-authority.md)
## HITL Gates (which decisions require human approval)
## Protocol DI Ports (which external ports this agent uses)
## Audit (what it logs and where)
```

## Orchestrator Registration

New agents must be registered in `agents/compliance/orchestrator.py`:
```python
AGENT_REGISTRY = {
    "my-agent": MyAgent(port=InMemoryMyPort()),
    ...
}
```

## Protocol DI for Agents

Agents use the same Protocol DI pattern as services:

```python
class MyAgentPort(Protocol):
    async def fetch_data(self, id: str) -> dict: ...

class InMemoryMyPort:
    async def fetch_data(self, id: str) -> dict:
        return {"id": id, "stub": True}

class MyAgent:
    def __init__(self, port: MyAgentPort) -> None:
        self._port = port

    async def run(self, context: dict) -> AgentResult:
        data = await self._port.fetch_data(context["id"])
        ...
```

## HITL Gates in Agent Code

Agents NEVER auto-apply changes above their autonomy level. Pattern:

```python
if self.autonomy_level >= AutonLevel.L3:
    # auto-process
    return self._process(data)
else:
    # HITL: propose, don't apply
    return HITLProposal(
        action=data,
        requires_approval_from="MLRO",
        reason="exceeds L2 autonomy threshold",
    )
```

See `services/hitl/hitl_service.py` for the gate implementation.

## Swarm Pattern

Multi-agent workflows use `agents/compliance/swarm.yaml`:
- Defines agent roles, trust levels, escalation paths
- All swarm decisions go through `SwarmOrchestrator`
- No agent calls another agent directly — only via orchestrator

## Agent Autonomy Levels (from agent-authority.md)

| Level | Name | What agents can do |
|-------|------|-------------------|
| L1 | Auto | Fully automated |
| L2 | Alert → Human | Acts but alerts |
| L3 | Auto + HITL gate | Auto up to gate |
| L4 | Human Only | No AI action |

Always set the lowest acceptable autonomy level. Err towards L2 over L1.

## ARL (Agent Routing Layer)

All multi-step agent tasks route through `route_agent_task` MCP tool:
- **Tier 1:** Claude Haiku (fast, simple tasks, routing/classification)
- **Tier 2:** Claude Sonnet (standard tasks, analysis)
- **Tier 3:** Claude Opus (complex tasks, financial decisions)

Routing decision is logged to ClickHouse (I-24). Never bypass ARL for production agent calls.

## Compliance Knowledge Base Integration

Agents accessing regulatory guidance must use the KB protocol:
```python
class KBQueryPort(Protocol):
    async def query(self, question: str, jurisdiction: str = "UK") -> list[Citation]: ...
```

Direct ChromaDB access from agents is forbidden — use `KBQueryPort` or MCP tool `kb_query`.

## Invariants for Agent Code

| Invariant | Rule |
|-----------|------|
| I-27 | Feedback is supervised — agents PROPOSE, never auto-apply |
| I-28 | All agent decisions logged in execution trace |
| EU AI Act Art.14 | Human oversight required for all L3+ decisions |
| MLRO double-check | SAR candidates always escalate to MLRO (L4) |

## References

- Swarm config: `agents/compliance/swarm.yaml`
- Soul directory: `agents/compliance/soul/`
- HITL service: `services/hitl/hitl_service.py`
- Agent registry: `.ai/registries/agent-map.md`
- ARL entry: `services/arl/` (commit 5f132dd)
- Agent authority: `.claude/rules/agent-authority.md`
- ADR: `docs/adr/ADR-004-fastmcp-agent-tooling.md`, `docs/adr/ADR-005-protocol-di-pattern.md`
