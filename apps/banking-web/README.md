# Banking Web — Sandbox UI

> **SANDBOX ONLY.** No live banking data. No real transactions. No real IBAN/PII.
> Backend: LangGraph sandbox (`graph_sandbox.py`) + LiteLLM :4000 (`banxe-general`).

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 15 (App Router) |
| Chat UI | `@assistant-ui/react` + `@assistant-ui/react-ai-sdk` |
| Streaming | Vercel AI SDK (`ai`, `@ai-sdk/openai`) |
| Styling | Tailwind CSS 3 + shadcn/ui primitives (CVA/clsx/tailwind-merge) |
| Linting | Biome 2.3.0 |
| Language | TypeScript 5.6 |

## Quick Start

```bash
cd apps/banking-web
cp .env.example .env.local   # fill in sandbox values
npm install
npm run dev
# Open http://localhost:3100
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LITELLM_BASE_URL` | `http://localhost:4000/v1` | LiteLLM proxy base URL |
| `LITELLM_API_KEY` | `sandbox-key` | API key for LiteLLM (sandbox placeholder) |
| `BANKING_MODEL` | `banxe-general` | Model name to route via LiteLLM |

## Done Criteria (B-3)

- [ ] `npm run dev` starts on :3100 without errors
- [ ] Chat UI renders (`Thread` component visible)
- [ ] Typing a message streams a response from LiteLLM :4000 sandbox
- [ ] Sandbox banner visible on every page load
- [ ] `npm run typecheck` → 0 errors
- [ ] `npm run lint` (Biome) → 0 errors

## Architecture

```
Browser
  └─ /  (app/page.tsx)
       ├─ SandboxBanner        — amber warning strip
       └─ BankingChat          — @assistant-ui/react Thread
            └─ useChat(api: /api/chat)
                 └─ app/api/chat/route.ts
                      └─ LiteLLM :4000 (banxe-general)  ← SANDBOX
```

## GAPs (deferred to B-4 / Production)

| GAP | Description |
|-----|-------------|
| OI-3 | Production deploy (Vercel / evo1); real LiteLLM routing |
| OI-4 | Wire LangGraph `graph_sandbox.py` as LangChain streaming tool |
| OI-5 | Auth gate (Keycloak :8180) before chat endpoint |
| OI-6 | Audit trail: log each chat turn to ClickHouse (I-24) |
