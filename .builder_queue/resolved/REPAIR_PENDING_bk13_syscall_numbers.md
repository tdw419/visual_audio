# REPAIR_PENDING — BK-13: the mailbox net-stack item needs a spec amendment (and a hosting decision)

**Status:** BOTH QUESTIONS RULED 2026-09-12 — see
`.builder_queue/RULING_20260912_defect19_bk13_worktree.md`. Q1 (mechanical,
orchestrator seat): clause amended to **SYS 18 = net_send / SYS 19 = net_recv**
(`cda559b`). Q2 (design, ruled under Jericho's standing "you lead"): the instance
boundary is **two kernels in ONE image** exchanging frames through the real
mailbox windows with in-substrate oracle admission — the host is the
runner/observer, never the transport, because a host-side pipe would put the
untrusted host in the data path and demote "every frame crosses the oracle" to a
host-side convention. BK-13 is therefore **promotable**; the two-runner/host-pipe
variant is rejected for now and can be revisited only as a separate item that
does not carry the oracle claim.
**Found:** 2026-09-12, builder cron `af3e62239ce2` (BK-12 tick re-derived it; this
tick recorded it so the next ticks stop re-deriving the same paragraph).

## Measured facts (line-anchored, this tree at `a9d3540`)

BK-13's backlog clause reads:

> Mailbox net stack skeleton: **SYS 14/15 send/recv** frames between two Glyph OS
> instances (host-mediated loopback first); every frame crosses the admission oracle
> | `tests/test_bk13_net.py` — instance A sends 64B frame, instance B receives
> byte-exact; malformed frame rejected by oracle with receipt | GH-18, GH-22

Both numbers named in that clause are already spent by landed rows:

- `SYS 14` = hierarchical path resolve — BK-9, `tools/glyph_gpt/baker.py:1537-1573`
  (`SYS 14 = resolve: a0 = packed FINAL component name, a1 = depth`), gate
  `tests/test_bk9_paths.py` 3/3 green, receipt `systems/RECEIPT_BK9_PATHS.md`.
- `SYS 16/17` = pipe write/read — BK-10, `tools/glyph_gpt/baker.py:2584-2635`, gate
  `tests/test_bk10_pipes.py` 2/2 green, receipt `systems/RECEIPT_BK10_PIPES.md`.
- Occupied numbers across landed kernels: 6/7/8 (GH-7/13 mailbox), 9–13 (GH-16 tick
  + GH-20 fs ops + BK-3 signals + BK-4 exit/join), 14 (BK-9), 16/17 (BK-10).
  **15, 18, 19, … are free** as of this tree (grep of `tools/glyph_gpt/*.py` and the
  roadmap rows).

## The two questions

**Q1 (mechanical-ish, but it is a spec edit):** retire BK-13's `SYS 14/15` clause —
reassign send/recv to the next free pair (proposal: **SYS 18 = net_send,
SYS 19 = net_recv**) so the item does not collide with BK-9/BK-10. Answer needed:
"amend and work it" or "leave it parked".

**Q2 (the real design judgment):** the clause says *"between two Glyph OS
instances … host-mediated loopback first"*. Nothing in the landed substrate defines
what an "instance boundary" is: two `GlyphRunner` processes with a host-side pipe
(the host is then in the trust path and the "every frame crosses the oracle" claim
needs a precise meaning), or two kernels inside ONE image (a real spatial loopback
through the mailbox window, which is closer to what GH-22/GH-18 already prove).
Those are different architectures with different receipts; picking one unilaterally
would rewrite a claim, which is why this is parked rather than promoted.

## Consequence for the loop

With BK-11 parked (DEFECT-18) and BK-13 parked here, the roadmap has **no eligible
open row**. The builder will not invent work: next ticks will re-verify landed gates
and wait for one of the two rulings. The cheapest unblock remains a one-line answer
on DEFECT-18 (`.builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md`, option
(a)/(b)/(c)), which also unblocks DEFECT-17 and the held
`.builder_queue/held_patches/defect16c_lbu_lhu.patch` and the BK-11 row.
