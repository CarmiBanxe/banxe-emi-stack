# B1 LangGraph Operator Runbook — Banking Engine (Banksy)
# Sprint: B-1 | Status: SANDBOX ONLY
# Created: 2026-07-11 | HITL: operator executes all commands (I-71 — factory does NOT run these)
# Branch: agent/factory/bankingengine/b0b1-sandbox

## SCOPE

Bootstrap LangGraph on evo1 and verify one round-trip through the sandbox graph.
SANDBOX ONLY — no live PSD2/Adorsys/banking connections.
All commands execute on **evo1 (100.68.102.48)**; never auto-executed by factory.

---

## Phase 1: Environment Setup (operator runs on evo1)

### 1.1 SSH to evo1 and create venv

```bash
ssh mmber@100.68.102.48

python3 -m venv ~/envs/banksy-b1
source ~/envs/banksy-b1/bin/activate

pip install langgraph langchain-openai langgraph-checkpoint-sqlite httpx
```

Packages:
- `langgraph` — graph orchestration framework
- `langchain-openai` — `ChatOpenAI` client (OpenAI-compat, used for LiteLLM)
- `langgraph-checkpoint-sqlite` — `SqliteSaver` checkpointer
- `httpx` — async HTTP (transitive dep; explicit install for version pinning)

### 1.2 Verify LiteLLM :4000 reachable from evo1

```bash
export LITELLM_API_KEY="sk-banxe-llm-gateway-2026"

curl -s -o /dev/null -w "%{http_code}" \
  http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY"
# Expected: 200
```

If not 200: `systemctl status litellm-lan-gateway` on the gateway host.

---

## Phase 2: LangGraph Configuration

### 2.1 Environment variables (set before running graph)

```bash
export LITELLM_BASE_URL="http://127.0.0.1:4000/v1"
export LITELLM_API_KEY="sk-banxe-llm-gateway-2026"
export LITELLM_MODEL="banxe-general"
# Optional — durable checkpoint (survives process restart):
# export BANKSY_CHECKPOINT_URI="banksy_sandbox.db"
```

Add to `~/envs/banksy-b1/bin/activate` for persistence across SSH sessions.

### 2.2 LiteLLM BudgetManager (optional sandbox spend cap)

Config lives in `litellm-config.v2.yaml` on the **LiteLLM gateway host** (not in this repo).
Edit that file and reload the service:

```yaml
# Under the banxe-general entry in model_list, add:
    max_budget: 0.01      # sandbox cap per request
    budget_duration: 1d
```

All self-hosted Ollama traffic has zero API cost; this cap is a guard for any future
cloud aliases routed through the same gateway.

### 2.3 SqliteSaver checkpointer

The scaffold uses in-memory SQLite by default (`:memory:`, state lost on restart).
For durable sandbox state that survives process restart:

```bash
export BANKSY_CHECKPOINT_URI="banksy_sandbox.db"
```

File `banksy_sandbox.db` is created in the working directory on first run.

---

## Phase 3: Smoke Test

### 3.1 Check out the branch on evo1

```bash
source ~/envs/banksy-b1/bin/activate

git clone --branch agent/factory/bankingengine/b0b1-sandbox \
  git@github.com:CarmiBanxe/banxe-emi-stack.git \
  ~/wt/banking-engine-b0b1-evo1

cd ~/wt/banking-engine-b0b1-evo1
```

Or if already cloned: `git pull origin agent/factory/bankingengine/b0b1-sandbox`.

### 3.2 Run the 1-node sandbox graph

```bash
python services/banking-engine/graph_sandbox.py
```

Expected output (reply text will vary):
```
Reply: <non-empty response from banxe-general>
Checkpoint: persisted (thread_id=sandbox-test-1)
```

### 3.3 Verify checkpoint row persisted (durable mode only)

Applicable when `BANKSY_CHECKPOINT_URI=banksy_sandbox.db`:

```bash
python3 - <<'EOF'
import asyncio
from langgraph.checkpoint.sqlite import SqliteSaver

async def check() -> None:
    cp = SqliteSaver.from_conn_string("banksy_sandbox.db")
    rows = list(cp.list(config={"configurable": {"thread_id": "sandbox-test-1"}}))
    assert rows, "FAIL — no checkpoint row found"
    print(f"PASS — {len(rows)} checkpoint row(s) for thread sandbox-test-1")

asyncio.run(check())
EOF
```

### 3.4 Negative check — no live banking calls

```bash
# Expect zero matches:
grep -rE "(adorsys|psd2|camt053|\.iban\.|swift)" \
  ~/.cache/ ~/wt/banking-engine-b0b1-evo1/services/banking-engine/ 2>/dev/null \
  && echo "WARNING: live banking endpoint reference found" \
  || echo "PASS — no live banking endpoint calls"
```

---

## Phase 4: Done Criteria — B-1 Complete When

- [ ] `pip install langgraph langchain-openai` succeeded without errors
- [ ] `curl http://127.0.0.1:4000/v1/models` returns HTTP 200 from evo1
- [ ] `graph_sandbox.py` exits without errors
- [ ] Reply from `banxe-general` is a non-empty string
- [ ] Checkpoint: persisted (in-memory confirmed by print line; file confirmed by §3.3)
- [ ] Negative check clean (no live banking endpoint references)
- [ ] Operator reports B-1 done → factory writes B-1 ledger-close event

---

## References

- Sandbox declaration: `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`
- Compliance gates: `docs/ops/banking-engine/COMPLIANCE-GATES.md`
- Graph scaffold: `services/banking-engine/graph_sandbox.py`
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- SqliteSaver package: https://pypi.org/project/langgraph-checkpoint-sqlite/
