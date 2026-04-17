# Ollama Model Configuration — Runbook
# Issue: #1 — @mycarmi_moa_bot не отвечает + замена крашащихся моделей
# Created: 2026-04-17 | IL-INFRA-01

## Problem

Large Ollama models (`qwen3.5-abliterated:35b`, `llama3.3:70b`) cause out-of-memory (OOM)
crashes on the GMKtec server (16 GB RAM / shared VRAM). The `@mycarmi_moa_bot` stops
responding after the Ollama worker is killed by the OS OOM killer.

**Symptoms:**
- Bot does not respond to messages
- `systemctl status ollama` shows the service crashed or was restarted
- `journalctl -u ollama -n 50` shows OOM kill signal

## Safe Model Matrix (GMKtec 16 GB)

| Model | VRAM approx. | Status | Notes |
|-------|-------------|--------|-------|
| `qwen2.5-coder:7b` | ~4 GB | ✅ SAFE | Default for design pipeline |
| `huihui_ai/qwen3.5-abliterated:9b` | ~5 GB | ✅ SAFE | Drop-in for `35b` variant |
| `qwen3:30b-a3b` | ~8 GB | ✅ SAFE | MoE sparse; replaces `llama3.3:70b` |
| `qwen3.5-abliterated:35b` | ~20 GB | ❌ OOM | Exceeds available VRAM |
| `llama3.3:70b` | ~40 GB | ❌ OOM | Requires 80 GB+ system |

## Workaround — OpenClaw Bot Config

The OpenClaw config lives on the GMKtec server at:
```
/home/guiyon/.openclaw/openclaw.json
```

This file is not in version control (contains server-specific paths and tokens).
To update the model without SSH access, ask the server owner to run:

```bash
# On GMKtec server — replace OOM model with safe 9b variant
sed -i 's/"model": "qwen3.5-abliterated:35b"/"model": "huihui_ai\/qwen3.5-abliterated:9b"/g' \
    /home/guiyon/.openclaw/openclaw.json

# Restart the bot
systemctl --user restart mycarmi-moa-bot
```

## Design Pipeline Config

The BANXE design-to-code pipeline model is configured via environment variable:
```bash
OLLAMA_MODEL=qwen2.5-coder:7b  # default — safe for GMKtec
```

Override in `.env` for local dev. Config reference: `config/penpot/penpot-config.yaml`.

## Prevention

- Never pull models larger than 10B parameters on GMKtec without checking available VRAM first.
- Check before pulling: `ollama list` (shows current models and sizes).
- Enforce model allowlist via `OLLAMA_MODEL` env var — do not hardcode large model names.

## Recovery Steps

1. `ssh gmktec` — connect to server
2. `journalctl -u ollama --since "1 hour ago"` — confirm OOM kill
3. `ollama list` — check loaded models
4. `ollama rm qwen3.5-abliterated:35b` — remove the crashing model
5. `ollama pull huihui_ai/qwen3.5-abliterated:9b` — pull safe replacement
6. Edit `/home/guiyon/.openclaw/openclaw.json` — update model name
7. `systemctl --user restart mycarmi-moa-bot` — restart bot
8. Test: send a message to `@mycarmi_moa_bot` and confirm response

## References

- GitHub Issue: #1
- Config: `config/penpot/penpot-config.yaml`
- Orchestrator: `services/design_pipeline/orchestrator.py`
