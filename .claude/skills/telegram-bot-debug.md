---
name: telegram-bot-debug
description: Diagnose and fix Telegram bot @mycarmi_moa_bot (OpenClaw MOA, port 18789)
context: fork
agent: Explore
allowed-tools: Bash(docker *), Bash(curl *), Bash(git *), Bash(cat *), Bash(grep *)
---

## Telegram Bot Environment

- Bot process: `!docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -iE "telegram|moa|openclaw|bot" || echo "No bot containers found"`
- Port 18789 status: `!curl -sf http://localhost:18789/health 2>/dev/null || echo "Port 18789 not responding"`
- Bot config: `!find . -name "openclaw*" -o -name "*moa*" -o -name "*telegram*" 2>/dev/null | grep -iE "config|json|yaml|env" | head -20`
- Bot logs (last 50): `!docker logs --tail 50 $(docker ps -aqf "name=moa\|openclaw\|telegram" 2>/dev/null | head -1) 2>&1 || echo "No bot container found"`
- Telegram webhook: `!grep -r "webhook\|TELEGRAM_BOT_TOKEN\|BOT_TOKEN" .env* config/ docker-compose* 2>/dev/null | head -10 || echo "No webhook config found"`
- Network connectivity: `!docker network ls 2>/dev/null && docker inspect $(docker ps -aqf "name=moa\|openclaw" | head -1) --format '{{json .NetworkSettings.Networks}}' 2>/dev/null || echo "Cannot inspect network"`

## Your task

Diagnose why @mycarmi_moa_bot is not responding:

1. **Container status** - Is the bot container running? Check restart count and uptime
2. **Port binding** - Is port 18789 exposed and reachable?
3. **Webhook config** - Is TELEGRAM_BOT_TOKEN set? Is webhook URL correct?
4. **Logs analysis** - Check for errors, exceptions, connection timeouts
5. **Dependencies** - Are upstream services (Ollama, DB) reachable from the bot container?
6. **Network** - Is the container on the correct Docker network?

Output a structured diagnosis:
- **Status**: RUNNING / STOPPED / CRASH-LOOP / NOT_DEPLOYED
- **Root cause**: identified issue
- **Fix**: concrete steps to restore the bot
- **Prevention**: monitoring recommendation
