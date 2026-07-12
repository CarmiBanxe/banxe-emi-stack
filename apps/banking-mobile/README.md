# Banxe Banking Mobile (Sandbox)

> ⚠ **SANDBOX ONLY** — Expo/React Native skeleton. Synthetic data. No real customers, PII, IBAN, or transactions.

## Quick Start

```bash
# 1. Install dependencies
cd apps/banking-mobile
npm install

# 2. Copy env
cp .env.example .env.local
# Edit .env.local: set EXPO_PUBLIC_BANKING_BACKEND_URL to your LangGraph/LiteLLM URL

# 3. Start Expo
npx expo start

# 4. Open in simulator or device
# Press 'i' for iOS simulator, 'a' for Android emulator, or scan QR with Expo Go
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EXPO_PUBLIC_BANKING_BACKEND_URL` | `http://localhost:4000/v1/chat/completions` | LiteLLM / LangGraph completions endpoint |
| `EXPO_PUBLIC_BANKING_MODEL` | `banxe-general` | Model name passed to backend |
| `EXPO_PUBLIC_KEYCLOAK_URL` | `http://localhost:8180` | Keycloak sandbox URL |
| `EXPO_PUBLIC_KEYCLOAK_REALM` | `banxe-sandbox` | Keycloak realm |
| `EXPO_PUBLIC_KEYCLOAK_CLIENT_ID` | `banking-mobile-sandbox` | Keycloak client ID |

> All `EXPO_PUBLIC_*` vars are baked into the bundle at build time. Never put secrets here.

## App Structure

```
app/
  _layout.tsx          ← Root Stack: tabs + /chat modal + /login
  (tabs)/
    _layout.tsx        ← 5-tab Tabs navigator + FloatingAIButton overlay
    index.tsx          ← Home (mock balances)
    agent.tsx          ← AI Agent tab (opens /chat)
    cards.tsx          ← Cards (mock)
    crypto.tsx         ← Crypto (mock prices)
    profile.tsx        ← Profile + SCA test
  chat.tsx             ← AI Chat modal
  login.tsx            ← Keycloak sandbox login
components/
  SandboxBanner.tsx    ← Amber SANDBOX warning bar
  FloatingAIButton.tsx ← Revolut AIR floating button (→ /chat)
  ChatInterface.tsx    ← Custom FlatList chat (fetch to backend)
  SandboxMockSCA.tsx   ← Mock Face ID modal (SANDBOX only)
  SandboxKeycloakLogin.tsx ← Keycloak :8180 login stub
```

## Done Criteria

| DC | Criterion | Verified |
|----|-----------|---------|
| DC-1 | 5-tab bottom nav renders (Home, AI Agent, Cards, Crypto, Profile) | Expo start |
| DC-2 | Floating AI button visible on all tabs → opens /chat modal | Manual |
| DC-3 | ChatInterface sends to EXPO_PUBLIC_BANKING_BACKEND_URL | Manual (requires backend) |
| DC-4 | SandboxMockSCA modal visible on Profile tab → simulate/cancel | Manual |
| DC-5 | SandboxKeycloakLogin renders; attempts POST to Keycloak :8180 | Manual |
| DC-6 | SandboxBanner visible on every screen | Visual |
| DC-7 | No hardcoded secrets / PII / IBAN in any file | Code review |
| DC-8 | All EXPO_PUBLIC_* vars env-based | Code review |

## Open GAPs (Deferred)

| GAP | Description |
|-----|-------------|
| OI-5 | Real Keycloak PKCE flow (expo-auth-session) |
| OI-6 | Production SCA (expo-local-authentication.authenticateAsync + I-27) |
| OI-7 | Real-time balance push (WebSocket / SSE from banking-engine) |
| OI-8 | Biometric key storage (expo-secure-store) for session tokens |

## Sandbox Boundaries

- **NO** real biometric calls — SCA is a mock Modal
- **NO** real Keycloak sessions — login stub only
- **NO** real financial data — all balances, cards, crypto prices are synthetic
- **NO** PII stored — no user data written to device storage in this skeleton
