# LLM Gateway — local dev + CI healthcheck (FU-2 Phase 4)

**Status:** prep only. This document records how to start the LiteLLM LAN
gateway locally and how the nightly smoke gate optionally pings it. It is the
core dependency for any *future* Intent Layer activation.

> **Not implemented / out of scope (unchanged by this PR):**
> - `INTENT_LAYER_ENABLED` and any activation flags (still off).
> - Any live HTTP wiring between emi-stack and `banxe-payment-core`.
> - Any client-facing API behaviour.
>
> This PR is documentation + optional CI wiring only. The gateway healthcheck
> in `smoke-gate-full.yml` is **skipped** unless `LLM_GATEWAY_URL` is set, so CI
> stays green when no gateway is configured.

## Where the gateway lives

The gateway is a LiteLLM proxy maintained in the **MetaClaw** repo under
`litellm/` (config, `.env.example`, `docker-compose.yml`) plus
`scripts/litellm-local-startup.sh`. It exposes an OpenAI-compatible API on
`:4000` in front of the LAN model backends.

## Start it locally

From a MetaClaw checkout:

```bash
cp litellm/.env.example litellm/.env   # fill in real values (gitignored)
scripts/litellm-local-startup.sh       # docker compose up + healthcheck
```

Alternative modes:

```bash
scripts/litellm-local-startup.sh --mode systemd   # use the systemd user unit
scripts/litellm-local-startup.sh --no-start        # healthcheck only
scripts/litellm-local-startup.sh --profile db      # also start optional Postgres
```

See `litellm/README.md` in MetaClaw for the full topology (ports/backends).

## Healthcheck (manual)

`/health/liveliness` and `/health/readiness` are unauthenticated; `/v1/models`
requires the master key.

```bash
# liveliness (no auth):
curl -fsS http://127.0.0.1:4000/health/liveliness && echo " gateway live"

# authenticated model list:
curl -fsS -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://127.0.0.1:4000/v1/models
```

## CI wiring (smoke-gate-full)

The nightly [`smoke-gate-full.yml`](../.github/workflows/smoke-gate-full.yml)
includes an **optional** step *"LLM gateway healthcheck (optional, FU-2)"*:

- Reads the `LLM_GATEWAY_URL` repo variable into the job env.
- If unset/empty → the step is **skipped** (`if: env.LLM_GATEWAY_URL != ''`),
  and the workflow stays green.
- If set → it polls `${LLM_GATEWAY_URL}/health/liveliness` (5 attempts) and
  fails the job only if a *configured* gateway is unreachable.

To enable it, set the repo variable (no secrets needed for the liveliness probe):

```bash
gh variable set LLM_GATEWAY_URL --body "http://<gateway-host>:4000" \
  --repo CarmiBanxe/banxe-emi-stack
```
