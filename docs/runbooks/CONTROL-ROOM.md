# Runbook: Control Room (herdr, read-only)

**Canon:** ADR-056 (Proposed) | **Scope:** operator/Director observability ONLY
**Tool:** herdr 0.7.5, host-level (`~/.local/bin/herdr`), multiplexer-only — socket API OFF, plugins OFF.

The Control Room is a read-only viewport over the EMI stack. It never executes, approves,
or relays client instructions. Any mutation happens outside it via the existing gated
runbooks (safeguarding-engine, transaction-monitor, banxe-recon-service-activation, ...).

---

## 1. Non-privileged user setup (conceptual checklist — no secrets here)

- [ ] Dedicated OS user, e.g. `bx-controlroom` (no sudo).
- [ ] NOT in the `docker` group; `docker ps` must fail for this user.
- [ ] No engine/DB credentials, API tokens, or `.env` files in its home or environment.
- [ ] No access to midaz (network policy / credentials absent by construction).
- [ ] Read access limited to: exported log locations (read-only), public GET health
      endpoints, grafana/superset URLs (viewer-role account only).
- [ ] herdr config default; `~/.config/herdr/config.toml` optional — set a neutral
      `new_cwd` so panes do not inherit unrelated project rc side effects.
- [ ] Verify boundary after setup: from this user, a `docker`, `psql`, `clickhouse-client`,
      or POST call must fail with "permission denied" / missing credentials.

## 2. Pane layout (5 panes, all read-only)

| Pane | Role | Example content (read-only) |
|------|------|------------------------------|
| `txn-monitor` | AML/transaction monitoring | tail of transaction-monitor service log |
| `recon` | Reconciliation status | tail of recon service log / latest recon report |
| `psd2` | PSD2 plane health | GET health of mock-aspsp / psd2 services (watch loop) |
| `dashboards` | Grafana/Superset | links/status; dashboards open in browser (viewer role) |
| `ops-shell` | Read-only diagnostics | shell of the non-privileged user, GET/tail only |

Keybindings (herdr defaults): prefix `ctrl+b`; split `prefix+v` / `prefix+minus`;
rename pane `prefix+shift+p` (focus the pane first); new tab `prefix+c`.

## 3. Start / stop

```bash
# start (as bx-controlroom)
herdr --session control-room          # creates or attaches the named session
herdr session list                    # expect: control-room  running

# stop (end of pilot / maintenance)
herdr session stop control-room
```

## 4. Detach / reattach over SSH

- Detach: `ctrl+b` then `q` — client exits, server session stays running.
- Reattach (same host): `herdr session attach control-room`.
- Reattach (from another device): `ssh <host>` as `bx-controlroom`, then
  `herdr session attach control-room` (or `herdr --remote <host> --session control-room`).
- Panes, names, and scrollback survive detach/reattach (verified in HERDR pilot, 2026-07-31,
  banxe-architecture `docs/roadmap/HERDR-PILOT-NOTES.md`).

## 5. Operator handoff

1. Outgoing operator detaches (`ctrl+b q`) — never stops the session mid-shift.
2. Outgoing operator notes anomalies in the shift log (outside Control Room, per existing
   runbook discipline).
3. Incoming operator reattaches and reviews all panes before acknowledging the shift.
4. Anything requiring action → the relevant gated runbook, executed under the privileged
   role there, attributed in the ledger. Never from a Control-Room pane.

## 6. NEVER do (mirrors ADR-056 "Panes MAY NOT")

- NEVER run `docker compose up/down/exec/restart` or mutate containers.
- NEVER call POST/PUT/DELETE on engine or payment APIs.
- NEVER store or use DB credentials; never query postgres/clickhouse/redis/**midaz**.
- NEVER submit/approve/cancel/relay a client instruction from any pane.
- NEVER touch n8n workflows.
- NEVER enable herdr socket API, plugins, or integrations (`herdr api|pane|tab|agent|...`).
- NEVER run the Control Room under a privileged user "just this once".

If a task cannot be done within these limits — it does not belong in the Control Room.

## Persistent autostart (operator)

- Control-Room is a MANDATORY operational component: a shift is not considered active without it running.
- Artifacts (host mark-legion): `scripts/control-room.sh` (idempotent tmux+herdr launcher, 6 read-only panes)
  + user unit `~/.config/systemd/user/herdr-controlroom.service` (Type=forking; NOT enabled by factory — Rule 11).
- Start:  `systemctl --user start herdr-controlroom.service`
- Enable at boot:  `systemctl --user enable herdr-controlroom.service ; loginctl enable-linger $USER`
- Attach:  `tmux attach -t banxe-controlroom`  (then herdr reattach)
- Stop:  `systemctl --user stop herdr-controlroom.service`
- Boundary (ADR-056 / INV-OPS-01): READ-ONLY; non-privileged; no engine/DB/midaz write; no client-instruction
  path; herdr multiplexer-only (socket API OFF, plugins OFF). Note: the engine-services pane uses list-only
  `docker ps`; under the canonical non-privileged user it degrades to "permission denied" — expected, and NOT
  a reason to grant docker group membership.
  UPDATE (V1, operator-ratified 2026-07-31): the docker-ps pane is REPLACED by HTTP-health/TCP checks —
  see §1 below; the note above is retained for history (append-only).

## §1 Dedicated user checklist (bx-controlroom) — V1 full compliance

V1 = read-only content AND non-privileged identity. Both are mandatory (ADR-056 / INV-OPS-01).

- [ ] `sudo useradd -r -s /usr/sbin/nologin -m bx-controlroom`   (operator; note: for tmux/herdr
      attach sessions a login shell may be preferred — operator may use `-s /bin/bash` instead;
      the hard requirement is the privilege set below, not the shell)
- [ ] Do NOT add bx-controlroom to the docker group; no DB creds; no write tokens; no midaz access.
- [ ] `loginctl enable-linger bx-controlroom`
- [ ] Install the unit FOR THAT USER: copy `herdr-controlroom.service` into
      `~bx-controlroom/.config/systemd/user/` (drop the `User=` line in user-scope — systemd honors
      `User=` only in system units), then as bx-controlroom:
      `systemctl --user enable herdr-controlroom.service && systemctl --user start herdr-controlroom.service`
      (Alternative: install system-wide in /etc/systemd/system/ keeping `User=bx-controlroom`.)
- [ ] engine-services pane observes via HTTP-health/TCP ONLY (no docker socket): curl GET on
      gateway/banxe-api/txn-monitor/marble/grafana/superset/mock-aspsp health endpoints,
      `pg_isready`, ClickHouse `SELECT 1` over HTTP, `redis-cli ping`.
- [ ] Degradation rule: a check that demands auth falls back to TCP reachability
      (`timeout 2 bash -c "</dev/tcp/localhost/PORT"`); NEVER put credentials into the
      Control-Room environment.
- [ ] Verify boundary after setup: as bx-controlroom, `docker ps` must fail; no `.pgpass`/token
      files in home; POST to any engine API must be impossible for lack of credentials.

## Production install path (non-privileged service)

- Service user bx-controlroom runs from `/opt/banxe/control-room/` (script + herdr copy, root-owned, read-only).
- systemd unit sets `Environment=HERDR_BIN=/opt/banxe/control-room/herdr` so the launcher resolves herdr
  without depending on the user's HOME.
- Dev/manual runs default to `$HOME/.local/bin/herdr` (HERDR_BIN unset).

## Live pane commands (p2/p4/p5 — read-only, no auth)

- p4 transaction-mon: gateway + banxe-mcp(:8100) health + txn-api(:8000) TCP reachability (no auth, no creds).
- p5 recon-status: recon Grafana(:3001) health + clickhouse(:9002)/postgres(:5432) TCP reachability;
  recon is RED-ZONE, DOWN expected when inactive.
- p2 engine-services note: `:8000/health` requires auth (401) and `:8000/v1/monitor/health` is 404 —
  both are FORBIDDEN in Control-Room panes (no credentials allowed); banxe-api is observed via
  TCP reachability, app-level health via banxe-mcp(:8100) and Grafana dashboards.
