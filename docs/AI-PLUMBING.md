# AI-PLUMBING — LiteLLM v2 Quick Reference
# Banxe EMI Stack | Updated: 2026-05-03

Engineer reference for calling the cluster AI plane from compliance, API, and dashboard services.

---

## Base URL and auth

```python
base_url = "http://legion:4000/v1"
headers  = {"Authorization": f"Bearer {os.environ['LITELLM_MASTER_KEY']}"}
```

`LITELLM_MASTER_KEY` is an operator-supplied env var. **Never hard-code it or commit it.**

OpenAI-compatible client example:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="http://legion:4000/v1",
    api_key=os.environ["LITELLM_MASTER_KEY"],
)

response = await client.chat.completions.create(
    model="ai",           # use a canonical alias below
    messages=[{"role": "user", "content": prompt}],
)
```

---

## Canonical model aliases

| Alias | Backing model | Use it for |
|-------|--------------|-----------|
| `ai` | qwen3.5:35b | KYC document translation, general compliance Q&A, FR/EN regulatory memos |
| `ai-heavy` | llama3.3:70b | AML statement screening, complex multi-step reasoning |
| `glm-air` | GLM-4.5-Air (distributed) | Legal evidence extraction, FR/EN/ZH translation |
| `reasoning` | qwen3:235b-a22b | Deep regulatory synthesis — ⚠️ status: **pending PASS**, use `ai-heavy` as fallback |
| `banxe-general` | (router-defined) | General staff assistant queries |
| `fast` | (router-defined) | Routing, classification, quick lookups (<200ms target) |
| `coding` | (router-defined) | Code generation, PR review, test generation |

Always prefer the most constrained alias for the task — do not default to `reasoning` for tasks
that `ai` can handle. `reasoning` is expensive and quota-limited.

---

## Retry and fallback behaviour

LiteLLM router is configured with:

- `num_retries: 2` — automatic retry on transient errors (5xx, timeout)
- Fallbacks:
  - `coding` → `qwen3-30b` (if primary unavailable)
  - `banxe-general` → `fast` (if primary unavailable)
- Timeout: 30s default per request (set `timeout=30` in client call)

If `reasoning` returns a 503 (pending PASS), catch and fall back to `ai-heavy` in application code:

```python
try:
    resp = await client.chat.completions.create(model="reasoning", messages=msgs, timeout=30)
except openai.APIStatusError as exc:
    if exc.status_code == 503:
        resp = await client.chat.completions.create(model="ai-heavy", messages=msgs, timeout=30)
    else:
        raise
```

---

## Deny-paths — PII/AML content must stay on local LiteLLM

The following path patterns contain regulated or sensitive content.
Requests involving this content MUST use a local alias (`ai`, `ai-heavy`, `glm-air`, `reasoning`).
They MUST NOT be sent to cloud APIs (Claude/Gemini/Groq/OpenAI).

```
compliance/cases/*
kyc/raw/*
secrets/*
.env*
**/*.pem
**/id_*
```

Reference: `banxe-infra/ai-routing/policy.yaml`

Violation = P0 security incident. The pre-commit hook checks for cloud-endpoint literals in code
that also imports compliance path constants.

---

## Checklist before adding a new AI call

- [ ] Alias chosen matches task (see table above)
- [ ] Content does not contain deny-path data — if it does, alias is local only
- [ ] `LITELLM_MASTER_KEY` read from env, not hardcoded
- [ ] Retry / fallback handling present for production paths
- [ ] ClickHouse audit log entry for any AI-driven decision (I-24)
- [ ] HITL gate in place if the call influences a financial or compliance outcome (I-27)
