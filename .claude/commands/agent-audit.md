---
description: Full audit of agent collaboration — run before every sprint
---

Run a complete agent audit:

1. List all agents in .claude/agents/ — check each has:
   - Defined role and triggers
   - HITL threshold (AUTO / REVIEW / BLOCK)
   - No overlap with another agent's function

2. Check last 10 commits: were ALL agents used per checklist?
   Report % compliance. Target: 100%.

3. Test Inspector isolation: can inspector_agent see implementation files?
   If yes → fix context isolation immediately.

4. OpenClo consensus: is threshold documented and ≥70%?

5. ARL: is Ruflo listed as mandatory middleware for payment/compliance/kyc?

6. HITL: are thresholds defined numerically for every L2 agent?

7. Verify safeguarding-agent deployment status on GMKtec.

8. Check banxe-subagent-context.md exists and is referenced in checklist.

9. Generate AGENT-AUDIT-{date}.md with:
   - PASS / FAIL per item
   - Bugs found
   - Actions required before next commit

Health metrics targets:
- pass@8 compliance agents: >80%
- HITL escalation rate: 10-15%
- Inspector catch rate: >90%
- Checklist compliance: 100%
