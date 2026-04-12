# ADR-005: Protocol DI (typing.Protocol + InMemory Stubs) as Dependency Injection Pattern

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-SK-01 (IL-073)
**Author:** Moriel Carmi / Claude Code

---

## Context

Financial services need to be testable without real external dependencies (Midaz, ClickHouse, Jube, Redis, Marble, ChromaDB). Classic DI approaches evaluated:

1. **No abstraction (direct imports)**: fast to write, impossible to test without infra
2. **DI framework (dependency-injector, injector)**: adds config overhead, opaque
3. **FastAPI `Depends()`**: good for HTTP layer, but doesn't compose for pure-Python service tests
4. **`typing.Protocol` + constructor injection**: no framework, fully Pythonic, IDE-friendly

---

## Decision

**`typing.Protocol` for all external port interfaces + `InMemory*` stub implementations for testing. No DI framework.**

Constructor injection only — services receive their ports at construction time.

---

## Pattern

```python
# 1. Define the port interface (services/my_service/ports.py)
from typing import Protocol
from decimal import Decimal

class LedgerPort(Protocol):
    async def get_balance(self, account_id: str) -> Decimal: ...
    async def post_transaction(self, tx: Transaction) -> str: ...

# 2. Production implementation (services/ledger/midaz_adapter.py)
class MidazLedgerAdapter:
    async def get_balance(self, account_id: str) -> Decimal:
        # real Midaz HTTP call

# 3. Test stub (same file or tests/stubs.py)
class InMemoryLedgerPort:
    def __init__(self, balances: dict[str, Decimal] = None) -> None:
        self._balances = balances or {}

    async def get_balance(self, account_id: str) -> Decimal:
        return self._balances.get(account_id, Decimal("0"))

# 4. Service (services/my_service/my_service.py)
class MyService:
    def __init__(self, ledger: LedgerPort) -> None:
        self._ledger = ledger

# 5. Usage in tests — no Docker, no network
async def test_service_calculates_correctly():
    svc = MyService(ledger=InMemoryLedgerPort({"acct-1": Decimal("100.00")}))
    ...

# 6. Usage in production (FastAPI DI)
async def get_my_service() -> MyService:
    return MyService(ledger=MidazLedgerAdapter())

@router.get("/endpoint")
async def endpoint(svc: MyService = Depends(get_my_service)):
    ...
```

---

## Rationale

| Criterion | Protocol DI | dependency-injector | Raw FastAPI Depends | Direct imports |
|-----------|------------|---------------------|---------------------|----------------|
| Test without infra | Yes (InMemory stubs) | Yes (if configured) | Partial | No |
| Framework dependency | None | Yes | FastAPI only | None |
| IDE type checking | Full (Protocol structural typing) | Partial | Full | Full |
| Learning curve | Low (stdlib) | High (config yaml/code) | Medium | None |
| Composable outside HTTP | Yes | Depends | No | N/A |

---

## Consequences

### Positive
- **1931 tests pass without any infrastructure** (no Docker, no Midaz, no ClickHouse)
- `typing.Protocol` is structural — stubs don't need to inherit from the Protocol class
- Fully IDE-navigable: go-to-definition works on protocol methods
- Trivial to add new port implementations (Vault, real Redis, etc.)

### Negative / Risks
- Stubs can drift from production implementations
- More boilerplate per service (Protocol + InMemory + Adapter = 3 files)

### Mitigations
- Integration tests (`tests/integration/`) run against real services and catch stub/prod drift
- Per-file pattern is codified in `.claude/rules/10-backend-python.md` — all new services follow it

---

## Applied Throughout

All 34+ services use this pattern. Key examples:
- `LedgerPortProtocol` / `StubLedgerAdapter` / `MidazLedgerAdapter`
- `AlertStorePort` / `InMemoryAlertStore`
- `ChromaStoreProtocol` / `InMemoryChromaStore`
- `StreamPort` / `InMemoryStreamPort`
- `JubePort` / `InMemoryJubePort` / `HTTPJubePort`

---

## References

- `.claude/rules/10-backend-python.md` — "Typed boundaries" section
- `.claude/rules/30-testing.md` — "InMemory stubs for external ports"
- `services/recon/clickhouse_client.py` — InMemoryReconClient reference implementation
- ADR-004: FastMCP (uses same pattern in MCP layer)
