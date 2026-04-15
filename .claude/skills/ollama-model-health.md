---
name: ollama-model-health
description: Check health of local Ollama models, detect crashes, suggest replacements
context: fork
agent: Explore
allowed-tools: Bash(curl *), Bash(docker *), Bash(cat *), Bash(grep *)
---

## Ollama Environment Snapshot

- Ollama service: `!curl -sf http://localhost:11434/api/tags 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "Ollama not responding on port 11434"`
- Running models: `!curl -sf http://localhost:11434/api/ps 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "Cannot get running models"`
- Ollama container: `!docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -i ollama || echo "No Ollama container"`
- Container logs (errors): `!docker logs --tail 100 $(docker ps -aqf "name=ollama" 2>/dev/null | head -1) 2>&1 | grep -iE "error|panic|crash|killed|OOM|fatal" | tail -20 || echo "No error logs"`
- GPU/memory: `!nvidia-smi 2>/dev/null || echo "No GPU detected"; free -h 2>/dev/null | head -2`
- Model config in project: `!grep -r "ollama\|model.*name\|MODEL" docker-compose* .env* config/ 2>/dev/null | grep -v Binary | head -15`
- Known crashing model: `!curl -sf http://localhost:11434/api/generate -d '{"model":"qwen3.5-abliterated:35b","prompt":"test","stream":false}' 2>&1 | head -5 || echo "Model test failed"`

## Known Issues

- **qwen3.5-abliterated:35b** — crashes under load, excessive VRAM usage
- Replacement candidates: qwen2.5:14b, llama3.1:8b, mistral:7b, deepseek-coder-v2:16b

## Your task

Audit Ollama model health:

1. **List all installed models** with sizes and quantization levels
2. **Test each model** with a simple prompt — record response time and success/failure
3. **Identify crashing models** — check logs for OOM kills, panics, timeouts
4. **Check VRAM budget** — compare total model sizes vs available GPU memory
5. **Suggest replacements** for unhealthy models:
   - Same capability class (coding, chat, compliance)
   - Smaller quantization or parameter count
   - Proven stable on available hardware
6. **Verify config references** — ensure docker-compose and .env point to healthy models

Output:
- **Model Health Table**: model | size | status | avg_response_ms | recommendation
- **VRAM Budget**: total_available vs total_loaded
- **Action Plan**: which models to remove, which to pull, config changes needed
