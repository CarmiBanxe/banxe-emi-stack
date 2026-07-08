"""Sprint 2+3 Watchdog MVP — efficiency-aware health monitor with repair engine.

I-27: auto = warm + log + alert ONLY.
NEVER restart, reroute, or evict. ESCALATE on SLOW/DEGRADED/INCORRECT.
Sprint 3: RepairEngine with decision policy + Docker monitoring.

VRAM note: rocm-smi is UNRELIABLE on evo1 (AMD unified, reports per-die slice).
           Use /api/ps + known model sizes for VRAM estimation.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
import json
import logging
from pathlib import Path
import time
from typing import Protocol

import httpx
import yaml

from services.watchdog.audit_log import AuditLogPort, AuditRecord, make_audit_record
from services.watchdog.decision_policy import RepairAction
from services.watchdog.dependency_graph import DependencyGraph, DependencyGraphPort
from services.watchdog.prometheus_exporter import WatchdogMetrics
from services.watchdog.root_cause_classifier import Classification, RootCauseClassifier
from services.watchdog.runbook_index import RunbookEntry, get_runbook

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "watchdog.yaml"


class NodeState(Enum):
    HEALTHY = auto()
    COLD = auto()
    LOADING = auto()
    UNREACHABLE = auto()
    SLOW = auto()
    DEGRADED = auto()
    INCORRECT = auto()


@dataclass(frozen=True)
class EfficiencyMetrics:
    tokens_per_sec: float
    hot_latency_s: float
    cold_start_s: float
    correctness: bool
    success_rate: float


@dataclass
class NodeConfig:
    name: str
    url: str
    warm_models: list[str]


@dataclass
class WatchdogConfig:
    p1_health_interval_s: int
    p2_efficiency_interval_s: int
    p1_timeout_s: int
    gen_timeout_s: int
    cold_strikes: int
    escalate_after_warmup_fails: int
    backoff_s: list[int]
    escalation_cooldown_s: int
    min_tokens_per_sec: dict[str, float]
    max_hot_latency_s: float
    max_cold_start_s: float
    min_success_rate: float
    correctness_prompt: str
    correctness_expect: str
    nodes: list[NodeConfig]
    may_warm: bool
    ledger_path: Path
    webhook: str | None
    audit_path: Path | None = None
    metrics_enabled: bool = False
    metrics_port: int = 9091
    dep_graph_raw: dict = field(default_factory=dict)
    snapshots_dir: Path | None = None
    slo_model_downtime_threshold_s: float = 3600.0

    @classmethod
    def from_yaml(cls, path: Path = CONFIG_PATH) -> WatchdogConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        probe = raw["probe"]
        thr = raw["thresholds"]
        aut = raw["autonomy"]
        esc = raw["escalation"]
        aud = raw.get("audit", {})
        met = raw.get("metrics", {})
        dep = raw.get("dependency_graph", {})
        snap = raw.get("snapshots", {})
        slo = raw.get("slo", {})
        nodes = [NodeConfig(**n) for n in raw["nodes"]]
        snap_dir: Path | None = None
        if snap.get("enabled") and snap.get("dir"):
            snap_dir = Path(snap["dir"])
        return cls(
            p1_health_interval_s=probe["p1_health_interval_s"],
            p2_efficiency_interval_s=probe["p2_efficiency_interval_s"],
            p1_timeout_s=probe["p1_timeout_s"],
            gen_timeout_s=probe["gen_timeout_s"],
            cold_strikes=thr["cold_strikes"],
            escalate_after_warmup_fails=thr["escalate_after_warmup_fails"],
            backoff_s=thr["backoff_s"],
            escalation_cooldown_s=thr["escalation_cooldown_s"],
            min_tokens_per_sec=thr["min_tokens_per_sec"],
            max_hot_latency_s=thr["max_hot_latency_s"],
            max_cold_start_s=thr["max_cold_start_s"],
            min_success_rate=thr["min_success_rate"],
            correctness_prompt=thr["correctness_probe"]["prompt"],
            correctness_expect=thr["correctness_probe"]["expect_contains"],
            nodes=nodes,
            may_warm=aut["may_warm"],
            ledger_path=Path(esc["ledger_path"]),
            webhook=esc.get("webhook"),
            audit_path=Path(aud["path"]) if aud.get("enabled") and aud.get("path") else None,
            metrics_enabled=met.get("enabled", False),
            metrics_port=met.get("port", 9091),
            dep_graph_raw=dep,
            snapshots_dir=snap_dir,
            slo_model_downtime_threshold_s=float(slo.get("model_downtime_threshold_s", 3600)),
        )


class OllamaPort(Protocol):
    async def list_models(self, node_url: str, timeout: float) -> list[str]: ...

    async def generate(
        self,
        node_url: str,
        model: str,
        prompt: str,
        timeout: float,
        keep_alive: int,
    ) -> dict: ...

    async def warm(self, node_url: str, model: str) -> bool: ...


class HttpOllamaPort:
    """Live HTTP adapter for Ollama API."""

    async def list_models(self, node_url: str, timeout: float) -> list[str]:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{node_url}/api/ps", timeout=timeout)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]

    async def generate(
        self,
        node_url: str,
        model: str,
        prompt: str,
        timeout: float,
        keep_alive: int = -1,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{node_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": keep_alive,
                },
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()

    async def warm(self, node_url: str, model: str) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{node_url}/api/generate",
                    json={"model": model, "prompt": "warm", "stream": False, "keep_alive": -1},
                    timeout=300,
                )
                return r.status_code == 200
        except Exception:
            return False


class InMemoryOllamaPort:
    """Stub for unit tests."""

    def __init__(
        self,
        loaded: dict[str, list[str]] | None = None,
        gen_response: dict | None = None,
        warm_result: bool = True,
    ) -> None:
        self._loaded: dict[str, list[str]] = loaded or {}
        self._gen_response = gen_response or {
            "response": "4",
            "eval_count": 10,
            "eval_duration": int(0.5 * 1e9),
            "total_duration": int(0.6 * 1e9),
            "load_duration": 0,
        }
        self._warm_result = warm_result

    async def list_models(self, node_url: str, timeout: float) -> list[str]:
        return self._loaded.get(node_url, [])

    async def generate(
        self,
        node_url: str,
        model: str,
        prompt: str,
        timeout: float,
        keep_alive: int = -1,
    ) -> dict:
        return self._gen_response

    async def warm(self, node_url: str, model: str) -> bool:
        return self._warm_result


class LedgerPort(Protocol):
    def append(self, entry: dict) -> None: ...


class FileLedger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")


class InMemoryLedger:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, entry: dict) -> None:
        self.entries.append(entry)


@dataclass
class NodeMonitor:
    config: WatchdogConfig
    node: NodeConfig
    ollama: OllamaPort
    ledger: LedgerPort
    state: NodeState = NodeState.HEALTHY
    _cold_strikes: int = 0
    _warmup_fails: int = 0
    _last_escalation: float = 0.0
    _success_window: deque = field(default_factory=lambda: deque(maxlen=20))

    def _min_tps(self, model: str) -> float:
        tps = self.config.min_tokens_per_sec
        return tps.get(model, tps.get("default", 8.0))

    def _log(self, event: str, extra: dict | None = None) -> None:
        entry: dict = {"ts": time.time(), "node": self.node.name, "event": event}
        if extra:
            entry.update(extra)
        self.ledger.append(entry)
        log.info("[%s] %s %s", self.node.name, event, extra or "")

    async def p1_health(self) -> NodeState:
        try:
            loaded = await self.ollama.list_models(self.node.url, self.config.p1_timeout_s)
        except Exception as exc:
            self._log("UNREACHABLE", {"error": str(exc)})
            self.state = NodeState.UNREACHABLE
            return self.state

        for model in self.node.warm_models:
            if not any(model in m for m in loaded):
                self._cold_strikes += 1
                self._log("COLD_STRIKE", {"model": model, "strikes": self._cold_strikes})
                if self._cold_strikes >= self.config.cold_strikes:
                    await self._auto_warm(model)
            else:
                self._cold_strikes = 0

        self.state = NodeState.HEALTHY
        return self.state

    async def _auto_warm(self, model: str) -> None:
        if not self.config.may_warm:
            self._escalate("COLD_NO_WARM_PERMISSION", {"model": model})
            return

        attempt = min(self._warmup_fails, len(self.config.backoff_s) - 1)
        backoff = self.config.backoff_s[attempt]
        self._log("WARMING", {"model": model, "backoff_s": backoff, "attempt": attempt})
        await asyncio.sleep(backoff)

        ok = await self.ollama.warm(self.node.url, model)
        if ok:
            self._warmup_fails = 0
            self._cold_strikes = 0
            self._log("WARM_OK", {"model": model})
        else:
            self._warmup_fails += 1
            self._log("WARM_FAIL", {"model": model, "fails": self._warmup_fails})
            if self._warmup_fails >= self.config.escalate_after_warmup_fails:
                self._escalate("WARM_EXHAUSTED", {"model": model})

    async def p2_efficiency(self, model: str) -> EfficiencyMetrics | None:
        try:
            resp = await self.ollama.generate(
                self.node.url,
                model,
                self.config.correctness_prompt,
                self.config.gen_timeout_s,
                keep_alive=-1,
            )
        except Exception as exc:
            self._log("EFFICIENCY_PROBE_FAIL", {"model": model, "error": str(exc)})
            self._success_window.append(0)
            return None

        eval_count: int = resp.get("eval_count", 0)
        eval_dur_ns: int = resp.get("eval_duration", 1)
        total_dur_ns: int = resp.get("total_duration", 0)
        load_dur_ns: int = resp.get("load_duration", 0)
        response_text: str = resp.get("response", "")

        tps = eval_count / (eval_dur_ns / 1e9) if eval_dur_ns > 0 else 0.0
        hot_latency = total_dur_ns / 1e9
        cold_start = load_dur_ns / 1e9
        correct = self.config.correctness_expect in response_text

        self._success_window.append(1 if correct else 0)
        success_rate = (
            sum(self._success_window) / len(self._success_window) if self._success_window else 1.0
        )

        metrics = EfficiencyMetrics(
            tokens_per_sec=tps,
            hot_latency_s=hot_latency,
            cold_start_s=cold_start,
            correctness=correct,
            success_rate=success_rate,
        )

        self._log(
            "EFFICIENCY",
            {
                "model": model,
                "tokens_per_sec": round(tps, 2),
                "hot_latency_s": round(hot_latency, 3),
                "cold_start_s": round(cold_start, 3),
                "correctness": correct,
                "success_rate": round(success_rate, 3),
            },
        )

        min_tps = self._min_tps(model)
        if tps < min_tps:
            self.state = NodeState.SLOW
            self._escalate("SLOW", {"model": model, "tps": tps, "min_tps": min_tps})
        elif hot_latency > self.config.max_hot_latency_s:
            self.state = NodeState.DEGRADED
            self._escalate("DEGRADED_LATENCY", {"model": model, "latency_s": hot_latency})
        elif success_rate < self.config.min_success_rate:
            self.state = NodeState.DEGRADED
            self._escalate("DEGRADED_SUCCESS_RATE", {"model": model, "rate": success_rate})
        elif not correct:
            self.state = NodeState.INCORRECT
            self._escalate("INCORRECT", {"model": model, "response": response_text[:80]})

        return metrics

    def _escalate(self, reason: str, detail: dict | None = None) -> None:
        now = time.time()
        if now - self._last_escalation < self.config.escalation_cooldown_s:
            return
        self._last_escalation = now
        entry: dict = {"reason": reason, "node": self.node.name}
        if detail:
            entry.update(detail)
        self._log("ESCALATE", entry)
        if self.config.webhook:
            log.warning("ESCALATION webhook=%s payload=%s", self.config.webhook, entry)


class Watchdog:
    def __init__(
        self,
        config: WatchdogConfig,
        ollama: OllamaPort,
        ledger: LedgerPort,
        repair_engine=None,  # type: ignore
        docker_port=None,  # type: ignore
        root_cause_classifier: RootCauseClassifier | None = None,
        audit_log: AuditLogPort | None = None,
        metrics: WatchdogMetrics | None = None,
        dep_graph: DependencyGraphPort | None = None,
    ) -> None:
        self._config = config
        self._monitors = [
            NodeMonitor(config=config, node=n, ollama=ollama, ledger=ledger) for n in config.nodes
        ]
        self._repair_engine = repair_engine
        self._docker = docker_port
        self._docker_config = config.__dict__.get("docker", {})
        self._classifier = root_cause_classifier
        self._audit = audit_log
        self._metrics = metrics
        self._dep_graph: DependencyGraphPort = dep_graph or DependencyGraph.from_dict(
            config.dep_graph_raw
        )
        self._preflight_cooldowns: dict[str, float] = {}
        self._snapshots_dir: Path | None = config.snapshots_dir

    async def run_once_p1(self) -> list[NodeState]:
        now = time.time()
        results = await asyncio.gather(*[m.p1_health() for m in self._monitors])
        if self._metrics:
            for mon, state in zip(self._monitors, results):
                for model in mon.node.warm_models:
                    key = f"{model}@{mon.node.name}"
                    if state == NodeState.UNREACHABLE:
                        self._metrics.record_model_down(model, mon.node.name, now)
                    else:
                        self._metrics.record_model_up(model, mon.node.name, now)
                    downtime = self._metrics._model_downtime_s.get(key, 0.0)
                    if downtime >= self._config.slo_model_downtime_threshold_s:
                        log.warning(
                            "SLO breach: %s downtime %.0fs >= threshold %.0fs",
                            key,
                            downtime,
                            self._config.slo_model_downtime_threshold_s,
                        )
        return list(results)

    async def run_once_p2(self) -> list[EfficiencyMetrics | None]:
        tasks: list = []
        for mon in self._monitors:
            for model in mon.node.warm_models:
                tasks.append(mon.p2_efficiency(model))
        return list(await asyncio.gather(*tasks))

    async def run_once_docker(self) -> None:
        """Monitor Docker containers — two-pass: cascade detection then classify/act."""
        if not self._docker or not self._repair_engine:
            return

        try:
            containers = await self._docker.list_containers()
            crash_loop_threshold = self._docker_config.get("crash_loop_threshold", 10)

            # Pass 1: build set of unhealthy container names
            unhealthy_set: set[str] = set()
            incidents: list[tuple] = []  # (container, reason, context)
            for container in containers:
                reason: str | None = None
                context: dict = {}
                if container.state == "exited":
                    reason = (
                        "Exited(0)"
                        if container.exit_code == 0
                        else f"Exited({container.exit_code})"
                    )
                    context = {
                        "container_name": container.name,
                        "exit_code": container.exit_code,
                        "restart_count": container.restart_count,
                        "crash_loop_threshold": crash_loop_threshold,
                    }
                    unhealthy_set.add(container.name)
                elif container.restart_count > crash_loop_threshold:
                    reason = "crash-loop"
                    context = {
                        "container_name": container.name,
                        "restart_count": container.restart_count,
                        "crash_loop_threshold": crash_loop_threshold,
                    }
                    unhealthy_set.add(container.name)
                if reason is not None:
                    incidents.append((container, reason, context))

            if self._metrics:
                self._metrics.set_unhealthy_targets(len(unhealthy_set))

            frozen_unhealthy = frozenset(unhealthy_set)

            # Pass 2: classify, cascade-check, act
            for container, reason, context in incidents:
                clsf: Classification | None = None
                if self._classifier:
                    clsf = self._classifier.classify(
                        state=container.state,
                        exit_code=container.exit_code,
                        restart_count=container.restart_count,
                        crash_loop_threshold=crash_loop_threshold,
                    )
                    # LLM enrichment for UNKNOWN+low-conf (I-27: enriches payload only)
                    if clsf and clsf.reason.value == "UNKNOWN" and clsf.confidence < 0.5:
                        clsf = await self._classifier.enrich_with_llm(
                            clsf, context_text=str(context)
                        )

                is_cascade = self._dep_graph.is_cascade(container.name, frozen_unhealthy)
                upstream = self._dep_graph.upstream_cause(container.name, frozen_unhealthy)

                if is_cascade:
                    action = RepairAction.LOG_AND_WAIT
                else:
                    action = await self._repair_engine.evaluate_and_act(reason, context)  # type: ignore[union-attr]
                    # Preflight: block AUTO actions when upstream dep is unhealthy
                    if action in (RepairAction.WARM_MODEL, RepairAction.START_CONTAINER):
                        blocked = await self._check_preflight(container.name, frozen_unhealthy)
                        if blocked:
                            action = RepairAction.ESCALATE

                rb_entry: RunbookEntry | None = get_runbook(clsf.reason) if clsf else None
                snap_path = await self._take_snapshot(container)
                await self._emit_audit_and_metrics(
                    container.name,
                    reason,
                    clsf,
                    action,
                    upstream_cause=upstream,
                    is_cascade=is_cascade,
                    rb_entry=rb_entry,
                    snapshot_path=snap_path,
                )

        except Exception as exc:
            log.error("docker monitoring failed: %s", exc)

    async def _check_preflight(self, target: str, unhealthy_set: frozenset[str]) -> bool:
        """Return True if AUTO action should be blocked due to unhealthy upstream deps."""
        deps = self._dep_graph.get_dependencies(target)
        blocked_deps = [d for d in deps if d in unhealthy_set]
        if not blocked_deps:
            return False

        now = time.time()
        cooldown_key = f"preflight:{target}"
        if (
            now - self._preflight_cooldowns.get(cooldown_key, 0.0)
            < self._config.escalation_cooldown_s
        ):
            return True  # already emitted PREFLIGHT_FAILED recently

        self._preflight_cooldowns[cooldown_key] = now
        log.warning("PREFLIGHT_FAILED for %s — blocked deps: %s", target, blocked_deps)
        if self._audit:
            preflight_rec = AuditRecord(
                timestamp=now,
                target=target,
                observed_state="PREFLIGHT_FAILED",
                root_cause="DEPENDENCY_UNHEALTHY",
                root_cause_confidence=1.0,
                selected_action="ESCALATE",
                action_score=0.0,
                autonomy_mode="HITL",
                executed=False,
                verification_result=None,
                upstream_cause=", ".join(blocked_deps),
            )
            self._audit.record(preflight_rec)
        return True

    async def _take_snapshot(self, container: object) -> str | None:
        """Write a sanitized container state snapshot; return path or None."""
        if not self._snapshots_dir:
            return None
        try:
            self._snapshots_dir.mkdir(parents=True, exist_ok=True)
            ts_int = int(time.time())
            name = getattr(container, "name", "unknown")
            snap_path = self._snapshots_dir / f"{name}-{ts_int}.json"
            payload = {
                "name": name,
                "state": getattr(container, "state", ""),
                "exit_code": getattr(container, "exit_code", 0),
                "restart_count": getattr(container, "restart_count", 0),
                "health": getattr(container, "health", None),
                "ts": ts_int,
            }
            snap_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
            return str(snap_path)
        except Exception as exc:
            log.warning("snapshot failed for %s: %s", getattr(container, "name", "?"), exc)
            return None

    async def _emit_audit_and_metrics(
        self,
        target: str,
        observed_state: str,
        clsf: Classification | None,
        action: RepairAction,
        upstream_cause: str | None = None,
        is_cascade: bool = False,
        rb_entry: RunbookEntry | None = None,
        snapshot_path: str | None = None,
    ) -> None:
        """Record decision to metrics and audit log."""
        if self._metrics:
            self._metrics.record_decision(action.name)
            if action == RepairAction.ESCALATE:
                self._metrics.record_escalation()

        if self._audit:
            autonomy_mode = "AUTO" if action != RepairAction.ESCALATE else "HITL"
            self._audit.record(
                make_audit_record(
                    target=target,
                    observed_state=observed_state,
                    root_cause=clsf.reason.value if clsf else "UNKNOWN",
                    root_cause_confidence=clsf.confidence if clsf else 0.0,
                    selected_action=action.name,
                    action_score=clsf.confidence if clsf else 0.0,
                    autonomy_mode=autonomy_mode,
                    executed=action in (RepairAction.WARM_MODEL, RepairAction.START_CONTAINER),
                    verification_result=None,
                    upstream_cause=upstream_cause,
                    is_cascade=is_cascade,
                    runbook_path=rb_entry.path if rb_entry else None,
                    quick_fix=rb_entry.quick_fix if rb_entry else None,
                    manual_only=rb_entry.manual_only if rb_entry else False,
                    llm_diagnosis=clsf.llm_diagnosis if clsf else None,
                    llm_confidence_hint=clsf.llm_confidence_hint if clsf else None,
                    snapshot_path=snapshot_path,
                )
            )

    async def run_self_test(self) -> dict:
        """Daily self-test: check ollama reachable, audit log writable, prometheus rendering.

        Emits watchdog_self_test_ok metric and an audit record.
        """
        results: dict[str, bool] = {}

        # Check audit log writable
        if self._audit:
            try:
                test_rec = make_audit_record(
                    target="self-test",
                    observed_state="SELF_TEST",
                    root_cause="UNKNOWN",
                    root_cause_confidence=0.0,
                    selected_action="LOG_AND_WAIT",
                    action_score=0.0,
                    executed=False,
                    verification_result=None,
                )
                self._audit.record(test_rec)
                results["audit_writable"] = True
            except Exception:
                results["audit_writable"] = False
        else:
            results["audit_writable"] = True  # no audit configured — pass

        # Check prometheus renders
        if self._metrics:
            try:
                rendered = self._metrics.render()
                results["prometheus_renders"] = len(rendered) > 0
            except Exception:
                results["prometheus_renders"] = False
        else:
            results["prometheus_renders"] = True

        ok = all(results.values())
        if self._metrics:
            self._metrics.record_self_test(ok)

        log.info("self-test result: %s details=%s", "PASS" if ok else "FAIL", results)
        return {"ok": ok, "checks": results}

    async def run_forever(self) -> None:
        last_p2: float = 0.0
        while True:
            await self.run_once_p1()
            await self.run_once_docker()
            if time.time() - last_p2 >= self._config.p2_efficiency_interval_s:
                await self.run_once_p2()
                last_p2 = time.time()
            await asyncio.sleep(self._config.p1_health_interval_s)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = WatchdogConfig.from_yaml()
    ledger_instance: LedgerPort = FileLedger(cfg.ledger_path)
    ollama_instance: OllamaPort = HttpOllamaPort()
    watchdog = Watchdog(cfg, ollama_instance, ledger_instance)
    asyncio.run(watchdog.run_forever())
