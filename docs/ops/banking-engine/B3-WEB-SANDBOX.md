# Banking Engine Sprint B-3 — Web Interface Layer (Sandbox)
**Status:** Delivered | **Branch:** `agent/factory/bankingengine/b3-web-sandbox`
**Date:** 2026-07-12 | **Constraint:** SANDBOX ONLY — no live banking data, no real PSD2/creds

---

## Scope

Sprint B-3 delivers a minimal Next.js 15 web application that renders a streaming
chat interface backed by the LangGraph sandbox (`graph_sandbox.py` from B-1) via
LiteLLM :4000 (`banxe-general`).

**In scope:**
- `apps/banking-web/` — Next.js 15 App Router skeleton
- `/api/chat` route streaming from LiteLLM :4000 (Vercel AI SDK)
- `@assistant-ui/react` Thread component for chat UI
- Sandbox banner on every page (no live data warning)
- Biome-clean TypeScript, tailwind styling

**Out of scope (B-4+):**
- Production deploy (Vercel / evo1 containers)
- Keycloak auth gate on `/api/chat`
- Live LangGraph integration (tool calls, state graph streaming)
- ClickHouse audit log per chat turn (I-24)
- Real account data display

---

## Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | Next.js (App Router) | `^15.3.3` |
| Chat runtime | `@assistant-ui/react` | `^0.10.3` |
| AI SDK integration | `@assistant-ui/react-ai-sdk` | `^0.10.3` |
| Streaming client | Vercel AI SDK `ai` | `^4.3.16` |
| OpenAI-compat provider | `@ai-sdk/openai` | `^1.3.22` |
| Styling | Tailwind CSS | `^3.4.17` |
| UI primitives | CVA + clsx + tailwind-merge | standard |
| Linting | Biome | `2.3.0` |
| Language | TypeScript | `^5.6.3` |

---

## File Tree

```
apps/banking-web/
├── app/
│   ├── globals.css
│   ├── layout.tsx            — RootLayout, metadata
│   ├── page.tsx              — Home: SandboxBanner + BankingChat
│   └── api/
│       └── chat/
│           └── route.ts      — POST: streamText → LiteLLM :4000
├── components/
│   ├── BankingChat.tsx       — AssistantRuntimeProvider + Thread
│   └── SandboxBanner.tsx     — amber warning strip
├── biome.json                — Biome 2.3.0 config (mirrors frontend/)
├── next.config.ts
├── package.json
├── postcss.config.js
├── tailwind.config.ts
├── tsconfig.json
├── .env.example              — LITELLM_BASE_URL, LITELLM_API_KEY, BANKING_MODEL
└── README.md
```

---

## Done Criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| DC-1 | `npm run dev` boots on :3100 without errors | `curl http://localhost:3100` returns 200 |
| DC-2 | Chat UI renders (Thread component visible) | Open browser → chat box appears |
| DC-3 | Chat streams from LiteLLM :4000 | Type a message → response streams in |
| DC-4 | Sandbox banner visible on every page | Check amber strip at top |
| DC-5 | `npm run typecheck` → 0 errors | `tsc --noEmit` exits 0 |
| DC-6 | `npm run lint` (Biome) → 0 errors | `biome ci .` exits 0 |
| DC-7 | No real IBAN/PII/secrets in code | Code review: only env refs |
| DC-8 | API key read from env, not hardcoded | Grep: `LITELLM_API_KEY` → `process.env` only |

---

## Network Isolation

This app is **SANDBOX ONLY**. The `/api/chat` route connects only to:
- `LITELLM_BASE_URL` (default `localhost:4000`) — LiteLLM proxy on evo1
- No direct external bank/PSD2 connections

In production (B-4): deploy behind Keycloak auth gate and restrict egress to evo1 LiteLLM only.

---

## Open GAPs

| GAP | Description | Sprint |
|-----|-------------|--------|
| OI-3 | Production deploy (Vercel / evo1 Docker) | B-4 |
| OI-4 | Live LangGraph tool calls from chat (graph_sandbox.py) | B-4 |
| OI-5 | Keycloak :8180 auth gate on `/api/chat` | B-4 |
| OI-6 | Per-turn ClickHouse audit log (I-24 compliance) | B-4 |

---

## References

- B-0 declaration: `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`
- B-1 LangGraph: `services/banking-engine/graph_sandbox.py`
- B-2 stubs: `services/banking-engine/stubs/`, `services/banking-engine/egress_logger.py`
- LiteLLM config: `docker/litellm/config.yaml` (evo1)
- assistant-ui docs: https://www.assistant-ui.com/docs
