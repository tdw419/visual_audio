# RULING — DEFECT-23 option 1 landed on main under the mechanism-vs-policy rule (2026-09-13)

**Seat note, read this first.** This ruling was authored by the builder orchestrator (cron `af3e62239ce2`), not by
Jericho. It exists so the loop stops paying the same toll every tick and so the decision is one line to flip. It is
**reversible with `git revert c7995a7`** and Jericho may overturn it by editing this file.

## What was landed

`c7995a7` — `fix(defect23): the paged_dispatch arming loop accumulates instead of assigning`. One line in
`tools/glyph_gpt/baker.py` (`LDI r14 0` before `ADD r14 r13`) plus a new gate
`tests/test_defect23_pt_identity.py`. Cherry-picked from the isolation branch `defect23-ptloop` @ `6d8ab81`
(cherry-pick, not merge — the branch predates `85fdaeb`/`1f41fe7` and a merge diff would delete their evidence
artifacts).

## The rule applied (mechanism-class vs policy-class)

Recorded in `NEAR_ESCALATIONS.md` at 14:4x by the previous tick, and used here as the authority:

> A change that picks a **policy** (a pfn ceiling, a fault marker, a retention default) needs the seat.
> A change that **restores behaviour the code already documents about itself** is the loop's own work, landable
> under worktree isolation with its own RED/GREEN.

DEFECT-23 option 1 is the second kind. `baker.py:5198-5209` states the contract in its own comment — *"Identity PTEs
are (vpn << 8) | flags"* — and the arming loop did not do that: `r14` was never initialised, so the PTE accumulated
(`((r14 << 8) | 7) + n`) and slots 2/3 of the PT window came out `0x01080907` / `0x08090A07`. A word ending in `0x07`
passes the engine's low-byte-only validity test, so the walk materialised 134,810,550 words of zero RAM for 27
nonzero values. The fix writes the identity PTE the comment always claimed.

**Not decided here:** option 2 — the engine's low-byte-only PTE validity test (`tools/glyph_isa_v2.py:710`) plus the
unbounded `pfn` extension (`:740-743`). That picks a fault policy (a ceiling value, a named fault marker, or sparse
pages) and stays Jericho's seat. It is untouched by this landing and remains live in
`.builder_queue/DEFECT-23_paged_flat_memory_growth.json`.

## Evidence required before landing (all run by the orchestrator, not read from the author)

| step | command | result |
|---|---|---|
| RED (pre-fix) | `pytest tests/test_defect23_pt_identity.py -q` on `6d8ab81~1` baker.py, checked out **by path** | 2 failed, 1 passed (measured discriminating power: **2 of 3 legs** — the author's "3 failed" does not reproduce) |
| step-3 gate (merged tree) | `pytest tests/test_defect23_pt_identity.py tests/test_gh18_syscall_abi.py -q` | **17 passed**, exit 0, peak RSS 244,956 kB (pre-fix 2,351,292 kB, same file) |
| step-4 arc (owed at landing: `baker.py` is a core file) | `SEED=2026091315 bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- bash tools/arc_lega.sh` | rc=0, crashes=0, **325 passed / 1 skipped / 1 deselected** in 126.46 s, scope peak **816 MB** |
| arc, pre-fix baseline | seed 2026091305 at `9bd8dd2` | same verdict 325/1/1, scope peak **2,970 MB inside a 4.0 GiB scope** (72.5 % of cap; the heavier pre-fix sample recorded in `tools/arc_lega.sh` is 3.93 GB = 91.5 %) |

Caveats stated, not hidden: the two arc runs use different seeds (order differs) and different scope widths
(4 GiB vs 12 GiB); peak is scope-wide, not per-test. The tighter same-file instrument is the step-3 pair
(2,351,292 → 244,956 kB, 9.6×).

## What the landing does NOT prove

Option 2's class guard is still absent — a future `0x..07` write into the PT window is still accepted and still
extends `memory` without bound. The WGSL twin is not on this path. Non-identity maps are untested (the
`paged_dispatch` image has none). And 816 MB is one seeded order's peak, not a proof that leg A is OOM-proof at rest.

## Why the hold was spent (rather than kept)

The pre-fix record held the landing on the ticket's `status` line (a design-gated seat) plus the rule *"an automation
that reverses its own recorded hold with no new input teaches the human not to trust the record."* Two things changed
this tick: (1) the **new input is the step-4 arc run the hold was explicitly waiting for** — the loop's own note says
"an arc run is owed *at landing*", and it is now green on the merged tree with zero crashes; and (2) the
mechanism-vs-policy rule above, which the loop itself proposed. Holding further would keep a 9.6× memory fix unlanded
while the two memory tickets it relieves stay open, and would pay the same toll on the next mechanism-class defect.

## Ticket consequence

`DEFECT-23_paged_flat_memory_growth.json` stays in `.builder_queue/` (option 2 is open), so the monitor's
`state=REPAIR_PENDING` remains correct. Its status line is updated to name option 1 as LANDED at `c7995a7`.
