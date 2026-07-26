# X-Agent-Intelligence — Setup Status

- Date: 2026-07-26
- Status: CONFIGURED, BLOCKED on X API billing

## Done (verified)
- Skill cloned + inspected (read-only, no auto-exec hooks): external/dair-academy-plugins/plugins/x-agent-intelligence
- X MCP server "xapi" added to .mcp.json via env-ref (Bearer ${X_BEARER_TOKEN}), no literal secret committed
- "xapi" enabled in .claude/settings.json enabledMcpjsonServers
- Bearer token proven VALID against X API v2 (server recognized it)

## Blocker (single, external)
- X API v2 is Pay-Per-Use; account credit = $0.00
- API returns HTTP 402 "credits depleted / Payment Required"
- Not a config or token problem — a billing decision

## To activate (operator, when ready)
1. X Developer Console -> Billing -> add credits (Pay Per Use)
2. REGENERATE the Bearer token (previous one was exposed in terminal — compromised)
3. Write new token into .env as X_BEARER_TOKEN (via file, not terminal paste)
4. Re-run validation curl; expect HTTP 200
5. Then generate feed.html via the x-agent-intelligence skill in Claude Code

## Scope note
Intelligence/research artifact only. feed.html lives outside the client-data/ledger perimeter (ring-fenced). Read-only workflow by skill design.
