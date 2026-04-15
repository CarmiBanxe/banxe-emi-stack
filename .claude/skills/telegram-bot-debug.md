---
name: telegram-bot-debug
description: Diagnose and fix Telegram bot @mycarmi_moa_bot (OpenClaw MOA, port 18789)
user-invocable: false
disable-model-invocation: true
context: fork
agent: Explore
allowed-tools: Bash(docker *), Bash(curl *), Bash(git *), Bash(cat *), Bash(grep *)
---

## Telegram Bot Environment

- Bot process: `!docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -iE "telegram|moa|openclaw|bot" || echo "No bot containers found"`
- Port 18789 status: `!curl -sf http://localhost:18789/health 2>/dev/null || echo "Port 18789 not responding"`
- Bot config: `!find . -name "openclaw*" -o -name "*moa*" -o -name "*telegram*" 2>/dev/null | grep -iE "config|json|yaml|env" | head -20`
- Bot logs (last 50): `!docker logs --tail 50 $(docker ps -aqf "name=moa\|openclaw\|telegram" 2>/dev/null | head -1) 2>&1 || echo "No bot container found"`
