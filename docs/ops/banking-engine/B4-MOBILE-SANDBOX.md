# B4 — Mobile App Layer (Sandbox)
## Banking Engine Sprint B-4 | Ops Runbook

> ⚠ **SANDBOX ONLY** — Expo/React Native skeleton. Synthetic data. No real customers, no real SCA, no real Keycloak sessions.

---

## Scope

| Item | Value |
|---|---|
| Sprint | B-4 |
| Track | Banking Engine (Banksy) |
| Branch | `agent/factory/bankingengine/b4-mobile-sandbox` |
| Worktree | `/home/mmber/wt/banking-engine-b4` |
| App path | `apps/banking-mobile/` |
| Purpose | Expo/RN skeleton: 5-tab nav, floating AI button, SCA mock, Keycloak stub |
| Sandbox | YES — no live banking data, no real PII/IBAN |

---

## Stack

| Layer | Technology | Note |
|---|---|---|
| Framework | Expo ~53 + expo-router v4 | File-based routing |
| Language | TypeScript (strict) | `tsconfig strict: true` |
| Styling | NativeWind v4 + Tailwind 3 | CSS-in-RN via `className` |
| Navigation | expo-router `(tabs)` group | 5-tab Tabs + Stack modals |
| Chat | Custom FlatList (fetch-based) | Calls `EXPO_PUBLIC_BANKING_BACKEND_URL` |
| Auth stub | Keycloak :8180 password grant | SANDBOX stub — no PKCE |
| SCA | Mock Modal only | `expo-local-authentication` NOT called |
| Linting | Biome 2.3.0 | `apps/banking-mobile/biome.json` |
| Icons | @expo/vector-icons (Ionicons) | |

---

## File Tree

```
apps/banking-mobile/
├── .gitignore
├── .env.example
├── app.json                         ← slug banxe-banking-mobile-sandbox
├── babel.config.js                  ← NativeWind jsxImportSource + preset
├── metro.config.js                  ← withNativeWind
├── tailwind.config.js               ← sandbox + banxe colours
├── global.css                       ← @tailwind base/components/utilities
├── tsconfig.json                    ← strict: true, @/* alias
├── biome.json
├── package.json
├── README.md
├── app/
│   ├── _layout.tsx                  ← Root Stack (3 screens)
│   ├── (tabs)/
│   │   ├── _layout.tsx              ← Tabs + SandboxBanner + FloatingAIButton
│   │   ├── index.tsx                ← Home (mock balances)
│   │   ├── agent.tsx                ← AI Agent tab
│   │   ├── cards.tsx                ← Cards (mock)
│   │   ├── crypto.tsx               ← Crypto prices (mock)
│   │   └── profile.tsx              ← Profile + SCA test button
│   ├── chat.tsx                     ← /chat modal (ChatInterface)
│   └── login.tsx                    ← /login screen (SandboxKeycloakLogin)
└── components/
    ├── SandboxBanner.tsx            ← Amber warning bar
    ├── FloatingAIButton.tsx         ← Revolut AIR button (bottom-right, z:999)
    ├── ChatInterface.tsx            ← FlatList chat → EXPO_PUBLIC_BANKING_BACKEND_URL
    ├── SandboxMockSCA.tsx           ← Mock Face ID modal
    └── SandboxKeycloakLogin.tsx     ← Keycloak :8180 password grant stub
```

---

## Starting the App

```bash
cd apps/banking-mobile
npm install
cp .env.example .env.local
# Edit EXPO_PUBLIC_BANKING_BACKEND_URL to point to local LiteLLM or LangGraph
npx expo start
# i → iOS sim, a → Android emulator, scan QR for Expo Go
```

---

## Environment Variables

| Variable | Default | Used by |
|---|---|---|
| `EXPO_PUBLIC_BANKING_BACKEND_URL` | `http://localhost:4000/v1/chat/completions` | ChatInterface |
| `EXPO_PUBLIC_BANKING_MODEL` | `banxe-general` | ChatInterface |
| `EXPO_PUBLIC_KEYCLOAK_URL` | `http://localhost:8180` | SandboxKeycloakLogin |
| `EXPO_PUBLIC_KEYCLOAK_REALM` | `banxe-sandbox` | SandboxKeycloakLogin |
| `EXPO_PUBLIC_KEYCLOAK_CLIENT_ID` | `banking-mobile-sandbox` | SandboxKeycloakLogin |

---

## Compliance Gates

| Invariant | Status | Evidence |
|---|---|---|
| I-01 No float for money | ✅ | All mock amounts are string `"1,250.00"` |
| I-02 Blocked jurisdictions | ✅ | No payment flows in scope; no routing logic |
| I-24 Append-only audit | ✅ | No DB writes; audit deferred to banking-engine backend |
| I-27 HITL — AI proposes | ✅ | SCA is mock; no autonomous action |
| No hardcoded secrets | ✅ | All config via `EXPO_PUBLIC_*` env vars |
| SANDBOX labelled | ✅ | SandboxBanner on every screen + alert banners in modals |

---

## Done Criteria

| DC | Criterion |
|----|-----------|
| DC-1 | 5-tab bottom nav renders in Expo |
| DC-2 | FloatingAIButton visible; taps open `/chat` modal |
| DC-3 | ChatInterface POSTs to `EXPO_PUBLIC_BANKING_BACKEND_URL` (non-streaming) |
| DC-4 | SandboxMockSCA modal: Simulate/Cancel work; MOCK label visible |
| DC-5 | SandboxKeycloakLogin POSTs to `:8180` token endpoint; error shown gracefully |
| DC-6 | SandboxBanner visible on every tab screen |
| DC-7 | No secrets/PII/IBAN hardcoded anywhere |
| DC-8 | All config env-based (`EXPO_PUBLIC_*`) |

---

## Open GAPs

| GAP | Description | Sprint |
|-----|-------------|--------|
| OI-5 | Real Keycloak PKCE flow (expo-auth-session + PKCE) | B-5+ |
| OI-6 | Real SCA: `expo-local-authentication.authenticateAsync()` + I-27 gate | B-5+ |
| OI-7 | Real-time balance push (WebSocket/SSE) from banking-engine | B-5+ |
| OI-8 | Session token in `expo-secure-store` (encrypted) | B-5+ |

---

## Network Isolation

All network calls in this skeleton go to `localhost` / `127.0.0.1` only (via `EXPO_PUBLIC_*` defaults).
No external SaaS, no production Keycloak, no cloud services are contacted by this app in sandbox mode.

---

## Related Docs

- `docs/ops/banking-engine/B3-WEB-SANDBOX.md` — web UI companion (Sprint B-3)
- `docs/ops/banking-engine/B2-INTERNET-SANDBOX.md` — PSD2/MCP stubs (Sprint B-2)
- `docs/ops/banking-engine/COMPLIANCE-GATES.md` — full gate registry
- `apps/banking-mobile/README.md` — developer quick-start
