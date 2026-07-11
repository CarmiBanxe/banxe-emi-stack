# B1 LangGraph Operator Runbook — Banking Engine (Banksy)
# Sprint: B-1 | Status: SANDBOX ONLY
# Created: 2026-07-11 | HITL: operator executes all commands manually (I-71)
# Branch: agent/factory/bankingengine/b0b1-sandbox

## SCOPE

Operator-executed runbook for bootstrapping LangGraph on evo1.
SANDBOX ONLY — no live PSD2/banking connections.
All commands run on evo1 (100.68.102.48); never auto-executed by factory (I-71).

---

## Phase 1: Environment Setup

### 1.1 SSH to evo1 and create venv

```bash
ssh mmber@100.68.102.48

python3 -m venv ~/envs/banksy-b1
source ~/envs/banksy-b1/bin/activate

pip install \
  langgraph \
  langchain-openai \
  langgraph-checkpoint-sqlite \
  httpx
```

### 1.2 Verify LiteLLM :4000 reachable from evo1

```bash
export LITELLM_API_KEY="sk-banxe-llm-gateway-2026"

curl -s http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  | python3 -m json.tool | grep -i banxe-general
```

Expected: line containing `"banxe-general"` in model list.
If no output: LiteLLM not running or alias missing — check `systemctl status litellm-lan-gateway`.

---

## Phase 2: Configuration

### 2.1 Environment variables (set before running graph)

```bash
export LITELLM_BASE_URL="http://127.0.0.1:4000/v1"
export LITELLM_API_KEY="sk-banxe-llm-gateway-2026"
export LITELLM_MODEL="banxe-general"
# Optional — for durable checkpoint (survives restart):
# export BANKSY_CHECKPOINT_URI="banksy_sandbox.db"
```

Add to `~/envs/banksy-b1/bin/activate` or `~/.bashrc` for persistence.

### 2.2 LiteLLM BudgetManager (sandbox spend cap — optional)

Add per-request spend cap in `litellm-config.v2.yaml` on the gateway host.
Edit on gateway host; reload service after change.

```yaml
# In litellm-config.v2.yaml → router_settings:
router_settings:
  budget_manager: true

# Under banxe-general entry in model_list:
# Add:
    max_budget: 0.01   # sandbox cap — 0.01 USD/request
    budget_duration: 1d
```

Note: all self-hosted Ollama calls have zero API cost; this cap is a safety guard for
any future cloud model aliases behind the same gateway.

### 2.3 SqliteSaver checkpointer (durable state)

The scaffold (`graph_sandbox.py`) uses in-memory SqliteSaver by default (`:memory:`).
For a durable sandbox that survives process restart, set:

```bash
export BANKSY_CHECKPOINT_URI="banksy_sandbox.db"
```

The file `banksy_sandbox.db` is created in the working directory on first run.

---

## Phase 3: Smoke Test

### 3.1 Check out the scaffold on evo1

```bash
source ~/envs/banksy-b1/bin/activate

# Option A: clone the branch directly onto evo1
git clone --branch agent/factory/bankingengine/b0b1-sandbox \
  git@github.com:CarmiBanxe/banxe-emi-stack.git \
  ~/wt/banking-engine-b0b1-evo1

cd ~/wt/banking-engine-b0b1-evo1

# Option B: if already checked out — pull latest
git pull
```

### 3.2 Run the 1-node sandbox graph

```bash
python services/banking-engine/graph_sandbox.py
```

Expected output (exact wording of reply will vary):
```
Reply: <non-empty response from banxe-general>
Checkpoint: persisted (thread_id=sandbox-test-1)
```

### 3.3 Verify checkpoint persisted (durable mode only)

Applicable only when `BANKSY_CHECKPOINT_URI=banksy_sandbox.db`.

```bash
python3 - <<'EOF'
import asyncio
from langgraph.checkpoint.sqlite import SqliteSaver

async def check() -> None:
    cp = SqliteSaver.from_conn_string("banksy_sandbox.db")
    checkpoints = list(cp.list(config={"configurable": {"thread_id": "sandbox-test-1"}}))
    assert len(checkpoints) > 0, "FAIL — no checkpoint found"
    print(f"PASS — {len(checkpoints)} checkpoint(s) found for thread sandbox-test-1")

asyncio.run(check())
EOF
```

### 3.4 Negative check — confirm no live banking calls made

```bash
# Grep graph output / any log for banking endpoints — expect zero hits:
grep -rE "adorsys|psd2|camt053|iban|swift|banxe-api" \
  ~/.cache/banksy*.log 2>/dev/null \
  || echo "PASS — no live banking endpoint calls detected"
```

---

## Phase 4: Done Criteria — B-1 Complete When

- [ ] `pip install langgraph` succeeded on evo1 (no errors)
- [ ] `curl http://127.0.0.1:4000/v1/models` returns banxe-general from evo1
- [ ] `python graph_sandbox.py` exits without errors
- [ ] Reply from banxe-general is a non-empty string
- [ ] Checkpoint: persisted (in-memory confirmed by print line; or file confirmed by check above)
- [ ] No live banking API calls detected (grep check clean)
- [ ] Operator reports completion → factory writes B-1 ledger-close event

---

## References

- Sandbox declaration: `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`
- Graph scaffold: `services/banking-engine/graph_sandbox.py`
- ADR-103 DLP boundary: `docs/adr/ADR-103-dlp-boundary.md`
- Agent authority: `.claude/rules/agent-authority.md`
- LiteLLM config: `litellm-config.v2.yaml` (gateway host — not in this repo)
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- LangGraph checkpoint-sqlite: https://pypi.org/project/langgraph-checkpoint-sqlite/
