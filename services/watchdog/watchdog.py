"""Sprint 2 Watchdog MVP skeleton — efficiency-aware health monitor.

I-27: auto = warm + log + alert ONLY.
NEVER restart, reroute, or evict. ESCALATE on SLOW/DEGRADED/INCORRECT.

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

    @classmethod
    def from_yaml(cls, path: Path = CONFIG_PATH) -> WatchdogConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        probe = raw["probe"]
        thr = raw["thresholds"]
        aut = raw["autonomy"]
        esc = raw["escalation"]
        nodes = [NodeConfig(**n) for n in raw["nodes"]]
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
        return float(tps.get(model, tps.get("default", 8.0)))  # nosemgrep: banxe-float-money

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
    ) -> None:
        self._config = config
        self._monitors = [
            NodeMonitor(config=config, node=n, ollama=ollama, ledger=ledger) for n in config.nodes
        ]

    async def run_once_p1(self) -> list[NodeState]:
        results = await asyncio.gather(*[m.p1_health() for m in self._monitors])
        return list(results)

    async def run_once_p2(self) -> list[EfficiencyMetrics | None]:
        tasks: list = []
        for mon in self._monitors:
            for model in mon.node.warm_models:
                tasks.append(mon.p2_efficiency(model))
        return list(await asyncio.gather(*tasks))

    async def run_forever(self) -> None:
        last_p2: float = 0.0
        while True:
            await self.run_once_p1()
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
