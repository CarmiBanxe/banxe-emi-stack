# G-RAR-PASS-01 — BANXE.RAR password missing on evo1

**Date:** 2026-05-06
**Branch:** docs/gap-rar-pass-01-2026-05-06
**Canon:** ADR-025 + IL-CANON-OPERATOR-2026-05
**Phase:** Phase 3 (controlled BANXE.RAR inventory) — BLOCKED

## Facts
- Archive: `/backup/banxe.rar` on evo1
- Size: 6,859,607,886 bytes (~6.4 GB)
- SHA-256: 420913292bf38c50543cbcecd8c2079e050f8d3fc588b1f7f145605af0e1bf13
- Format: RAR v5, header-encrypted (password required even for `unrar lb`)
- Tooling on evo1: `/usr/bin/unrar`, `/usr/bin/7z` available

## Block
- `/home/banxe/.banxe/rar.pass` does not exist / not readable.
- No `pass` store entries on evo1 for user `banxe`.
- No `*rar*pass*` / `*banxe*pass*` candidates under `/home/banxe` or `/root`.
- Without password, Phase 3 RAR inventory cannot proceed (cannot list, classify, or extract per roadmap rules).

## Impact
- BLOCKS: Phase 3 (RAR inventory), Phase 4 waves A-E (migration cannot start without inventory), Phase 5 (consolidation).
- DOES NOT BLOCK: Phases 1-2 already complete (auth boundary + adapter seams) and merged into main via PR #60, #61, #62.

## Resolution path (operator action required)
1. Operator places password into `/home/banxe/.banxe/rar.pass` on evo1 with `chmod 600`.
2. Verify: `ssh banxe@evo1 'test -r /home/banxe/.banxe/rar.pass && echo OK'`.
3. Resume Phase 3 with: `unrar lb -p$(cat /home/banxe/.banxe/rar.pass) /backup/banxe.rar > /tmp/banxe-rar-listing.txt`.
4. Classify entries by category (auth/IAM/payments/compliance/adjacent/orchestration) per AUTH_MATRIX + roadmap.

## Canon compliance
- §8: password never printed in chat or shell logs; only path referenced.
- §3.2: secret access flagged as non-safe; awaiting operator action.
- §10: ADR-031 deny-paths respected — no extraction attempted, no PII surfaced.

## Tracker ID
G-RAR-PASS-01 (open, blocking Phase 3+).
