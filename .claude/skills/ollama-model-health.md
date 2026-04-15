---
name: ollama-model-health
description: Check health of local Ollama models
user-invocable: false
disable-model-invocation: true
context: fork
agent: Explore
allowed-tools: Bash(curl *), Bash(docker *), Bash(cat *), Bash(grep *)
---

## Ollama Environment Snapshot

- Service: curl localhost:11434/api/tags
- Running: curl localhost:11434/api/ps
- GPU: nvidia-smi

## Known Issues

- qwen3.5-abliterated:35b crashes on 32GB RAM
- Replace with: qwen2.5:14b or mistral:7b
