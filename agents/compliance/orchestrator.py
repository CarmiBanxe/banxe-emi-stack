"""
agents/compliance/orchestrator.py — Compliance Swarm Orchestrator
Parses swarm.yaml, boots agents by layer, manages lifecycle.
IL-068 | FCA CASS 15 | banxe-emi-stack

Architecture:
  1. Parse swarm.yaml → coordinator + agent configs
  2. Resolve dependencies (DAG by depends_on)
  3. Boot Layer 1 (adapters) in parallel
  4. Boot Layer 2 (domain agents) after deps ready
  5. Coordinator (mlro_agent) oversees all, enforces HITL gates
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any

import yaml

from agents.compliance.agent_runner import (
    AgentConfig,
    AgentStatus,
    AutonomyLevel,
    ComplianceAgent,
)

# IL-015 Phase 5: Recon AI skills registered for dynamic loading by swarm agents
# Skills are declared in swarm.yaml under agents[*].skill field
# and loaded at runtime via importlib when agent processes a recon event.
#
# Registered skills:
#   - agents.compliance.skills.recon_analysis.ReconAnalysisSkill
#     Soul: agents/compliance/soul/recon_analysis_agent.soul.md
#   - agents.compliance.skills.breach_prediction.BreachPredictionSkill
#     Soul: agents/compliance/soul/breach_prediction_agent.soul.md
#
# Workflow entry point:
#   - agents.compliance.workflows.daily_recon_workflow.run_daily_workflow()
_RECON_SKILL_REGISTRY: dict[str, str] = {
    "recon_analysis_agent": "agents.compliance.skills.recon_analysis.ReconAnalysisSkill",
    "breach_prediction_agent": "agents.compliance.skills.breach_prediction.BreachPredictionSkill",
}

# IL-MCP-01: MCP Server health skill registered for infrastructure monitoring.
# MCPHealthSkill validates all MCP tools are documented, typed, and functional.
# Schedule: on startup + every 6 hours.
# Soul: agents/compliance/soul/mcp_server_agent.soul.md
# Workflow: agents/compliance/workflows/mcp_health_workflow.py
_MCP_SKILL_REGISTRY: dict[str, str] = {
    "mcp_server_agent": "agents.compliance.workflows.mcp_health_workflow.MCPHealthSkill",
}

logger = logging.getLogger("banxe.swarm.orchestrator")


@dataclass
class SwarmManifest:
    """Parsed swarm.yaml."""

    name: str
    version: str
    description: str
    trust_zone: str
    fca_basis: str
    coordinator: AgentConfig
    agents: list[AgentConfig]
    knowledge_base: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    hitl_gates: dict[str, Any] = field(default_factory=dict)


class SwarmOrchestrator:
    """
    Main entry point for the compliance agent swarm.
    Reads swarm.yaml, instantiates agents, manages boot/shutdown.
    """

    def __init__(self, swarm_yaml: str | Path | None = None) -> None:
        self._swarm_root = Path(__file__).parent
        self._yaml_path = Path(swarm_yaml) if swarm_yaml else self._swarm_root / "swarm.yaml"
        self.manifest: SwarmManifest | None = None
        self.coordinator: ComplianceAgent | None = None
        self.agents: dict[str, ComplianceAgent] = {}
        self._booted = False

    def _parse_agent_config(self, raw: dict[str, Any], is_coordinator: bool = False) -> AgentConfig:
        return AgentConfig(
            id=raw["id"],
            soul_path=raw.get("soul", ""),
            autonomy=AutonomyLevel(raw.get("autonomy", "L3")),
            human_double=raw.get("human_double", ""),
            depends_on=raw.get("depends_on", []),
            parallel=raw.get("parallel", False),
            tool_names=raw.get("tools", []),
            thresholds=raw.get("thresholds", {}),
            hitl_gates=raw.get("hitl_gates", []) if is_coordinator else [],
            sla_ms=raw.get("sla_ms"),
        )

    def parse(self) -> SwarmManifest:
        logger.info("Parsing swarm manifest: %s", self._yaml_path)
        raw = yaml.safe_load(self._yaml_path.read_text(encoding="utf-8"))
        coord_cfg = self._parse_agent_config(raw["coordinator"], is_coordinator=True)
        agent_cfgs = [self._parse_agent_config(a) for a in raw.get("agents", [])]
        self.manifest = SwarmManifest(
            name=raw["name"],
            version=raw["version"],
            description=raw.get("description", ""),
            trust_zone=raw.get("trust_zone", "RED"),
            fca_basis=raw.get("fca_basis", ""),
            coordinator=coord_cfg,
            agents=agent_cfgs,
            knowledge_base=raw.get("knowledge_base", {}),
            memory=raw.get("memory", {}),
            audit=raw.get("audit", {}),
            webhooks=raw.get("webhooks", []),
            hitl_gates=raw.get("hitl_gates", {}),
        )
        logger.info(
            "Manifest parsed: %s v%s | coordinator=%s | agents=%d",
            self.manifest.name,
            self.manifest.version,
            self.manifest.coordinator.id,
            len(self.manifest.agents),
        )
        return self.manifest

    def _resolve_boot_layers(self) -> list[list[AgentConfig]]:
        if not self.manifest:
            raise RuntimeError("Call parse() first")
        layers: list[list[AgentConfig]] = []
        booted: set[str] = set()
        remaining = list(self.manifest.agents)
        max_iterations = len(remaining) + 1
        for _ in range(max_iterations):
            if not remaining:
                break
            layer = [a for a in remaining if all(d in booted for d in a.depends_on)]
            if not layer:
                unresolved = [a.id for a in remaining]
                logger.error("Circular dependency detected: %s", unresolved)
                break
            layers.append(layer)
            booted.update(a.id for a in layer)
            remaining = [a for a in remaining if a.id not in booted]
        logger.info("Boot plan: %d layers", len(layers))
        for i, layer in enumerate(layers):
            logger.info("  Layer %d: %s", i + 1, [a.id for a in layer])
        return layers

    async def boot(self) -> dict[str, Any]:
        if not self.manifest:
            self.parse()
        assert self.manifest is not None
        logger.info("=== BOOTING SWARM: %s ===", self.manifest.name)
        start = datetime.now(UTC)
        # Boot coordinator first
        self.coordinator = ComplianceAgent(self.manifest.coordinator, self._swarm_root)
        await self.coordinator.start()
        self.agents[self.manifest.coordinator.id] = self.coordinator
        # Boot agents by layer
        layers = self._resolve_boot_layers()
        for i, layer in enumerate(layers):
            logger.info("--- Booting Layer %d (%d agents) ---", i + 1, len(layer))
            layer_agents = []
            for cfg in layer:
                agent = ComplianceAgent(cfg, self._swarm_root)
                self.agents[cfg.id] = agent
                layer_agents.append(agent)
            if layer[0].parallel:
                await asyncio.gather(*(a.start() for a in layer_agents))
            else:
                for a in layer_agents:
                    await a.start()
        elapsed = (datetime.now(UTC) - start).total_seconds()
        self._booted = True
        summary = {
            "swarm": self.manifest.name,
            "version": self.manifest.version,
            "trust_zone": self.manifest.trust_zone,
            "coordinator": self.coordinator.info(),
            "agents": {aid: a.info() for aid, a in self.agents.items()},
            "boot_time_s": round(elapsed, 3),
            "status": "running",
        }
        logger.info("=== SWARM BOOTED in %.3fs | %d agents ===", elapsed, len(self.agents))
        return summary

    async def shutdown(self) -> None:
        logger.info("=== SHUTTING DOWN SWARM ===")
        for aid, agent in reversed(list(self.agents.items())):
            await agent.stop()
        self._booted = False
        logger.info("=== SWARM STOPPED ===")

    async def dispatch(self, event_type: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._booted:
            raise RuntimeError("Swarm not booted")
        results = []
        for aid, agent in self.agents.items():
            if agent.status == AgentStatus.RUNNING:
                r = await agent.process_event(event_type, data)
                results.append(r)
        return results

    def status(self) -> dict[str, Any]:
        return {
            "booted": self._booted,
            "agents": {aid: a.info() for aid, a in self.agents.items()},
        }


# ── CLI entry point ───────────────────────────────────────────────────────


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    orch = SwarmOrchestrator()
    summary = await orch.boot()
    print("\n=== SWARM STATUS ===")
    for aid, info in summary["agents"].items():
        soul = "OK" if info["soul_loaded"] else "MISSING"
        print(
            f"  {aid}: {info['status']} | autonomy={info['autonomy']} | tools={len(info['tools'])} | soul={soul}"
        )
    print(f"\nBoot time: {summary['boot_time_s']}s")
    print(f"Trust zone: {summary['trust_zone']}")
    await orch.shutdown()


if __name__ == "__main__":
    asyncio.run(_main())
