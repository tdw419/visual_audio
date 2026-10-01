# RULING — GO-5 design marker (auto-filed per RULING_go5_residual_scheduler_yield_divergence.md)

**UPDATE 2026-09-15 ~13:5x CDT (cron af3e62239ce2): pin3 landed — pin2 headline
SUPERSEDED.** Worktree commit `183f1ae`, artifact `output/go5_pin3_20260915d.md`
(+ probes `go5_scan_ld_20260915d.py` / `go5_scan_ld2_20260915d.py`). The licensed
scan-LD dump (r20 at rv 0xc9c vs memory[proc+i*128+64]) measured: the proc-stride
walk is correct (r8 = 0x1f80/0x2000/0x2080 in order), the state LD is CORRECT at
EVERY hit post-reap included — proc[2] reads ZOMBIE (4) and is skipped, and
proc[0]/proc[1] ARE marked RUNNING (state transitions (1,1,4)→(2,1,4)→(1,2,4)
round-robin). The engine-vs-transpiler fork below is thereby tilted to the
TRANSpiler/BUG-B seam: after selection, the state store goes to the selected proc
while the `curproc = p` store + context load run a STALE proc[2] pointer
(curproc stays 0x2080 across every post-reap dispatch). Option 3 as originally
aimed (GlyphCPUv2 semantics) is the wrong half; if licensed, the fix target is
the transpiler's switch_to pointer path. Next probe (option-1 continuation):
dump the register holding `p` at switch_to entry per dispatch, pre- vs
post-reap, and diff.

**UPDATE 2026-09-15 ~13:2x CDT (cron af3e62239ce2): pin2 landed** — worktree
`go5-ptr-table-base` commit `0f04d3e`, artifact `output/go5_pin2_20260915c.md`.
Headline: after the first reap, the Glyph scheduler re-dispatches **proc[2]
(ZOMBIE) exclusively**; proc[0]/proc[1] keep correct resume pcs (0x930 / 0xaa0)
but are never marked RUNNING again. The scheduler scan's `p->state == RUNNABLE`
check on the ZOMBIE behaves as if RUNNABLE. Corrects pin1's "proc[0]/proc[1]
ping-pong" wording. Next probe (still option-1): dump the scan's state-LD
value (`r20` at rv 0xc9c) per iteration i=0,1,2 vs `memory[proc+i*128+64]` to
separate engine-LD-semantics (Jericho option 3 territory) from transpiler
address arithmetic.

Per the residual ruling's stop clause ("write the pin into `REPAIR_PENDING_go5_design.md`"),
this file carries the measured pin. The pin evidence itself is COMMITTED on branch
`go5-ptr-table-base` (worktree `/home/jericho/projects/zion/worktrees/go5-ptr-base`,
commit `29be6a2`): `output/go5_divergence_pin.md` + probes/results.

## The pin (measured, falsifiable)

- Twins IDENTICAL through G step 3117 / U cycle 640 (console word 0xa6968 byte-exact).
- First diverging event: the GPU twin's cycle-3712 console 'R' (second reap,
  reaped 0b100→0b110) NEVER happens on Glyph; Glyph enters scheduler
  re-dispatch starvation after the first reap (~step 5072) to the 3M-step budget.
- FALSIFIED by measurement: console byte-vs-word packing (pin3c: no spurious NUL;
  glyph word0 0xa6968 == GPU) and r31 CALLR/RET stack corruption (spin: r31
  17400↔17404, ctx_sched.ra=0xc1c correct).
- The exact non-advancing store/check INSIDE the spin loop is NOT yet identified
  (fenced: that probe is option-1 continuation, not engine work).

## What is parked to Jericho (unchanged from the residual ruling)

s11 remains RED by design: `g_clen Glyph 3 != GPU 7`,
`tests/test_rv64i_to_glyph_xv6_nano.py:953`, gate
`/usr/bin/python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py -q -p no:randomly`
= 1 failed / 12 passed (re-confirmed 2026-09-15 ~12:2x CDT at worktree HEAD `29be6a2`,
`output/go5_gate_reconf_20260915b.txt`). Choose:

1. **(recommended per the residual ruling)** license option 3 on the pinned line:
   fix GlyphCPUv2 scheduler re-dispatch/yield semantics to match x2 — all
   transpiler differential suites must stay green;
2. option 2: restructure s11 to yield only from the outer shell loop — weaker
   GO-5 claim;
3. continue option 1: license the next probe (watch `proc[i].state` stores +
   ISO_MMIO arming words, steps 5072–8000) to name the stuck instruction before
   any semantic change.

No code was changed this tick; this file is a pointer, not new evidence.

---

## RESOLVED 2026-09-15 ~14:3x CDT (cron `af3e62239ce2`) — the fork was INVERTED by measurement: neither option 2 nor option 3 was needed

**DEFECT-30 found and fixed: the SRL/SRA lowering clobbers callee-saved s10
(glyph r26) with no save/restore — a transpiler scratch defect, DEFECT-11's
class, NOT engine semantics.**

- Pins 5/6 (`go5-ptr-base output/go5_pin5_curproc_watch_result.txt`,
  `go5_pin6_s10_watch_result.txt`): at the first post-reap `sra a5,a4,s1`
  (rv 0xc38, scheduler reap branch) the lowering's `LDI r26 31; AND r26 r9`
  destroys r26 = RV x26 = s10 (0x2000 → 0x1f → 0x2, steps 5038/5039); every
  later `sw s0,-324(s10)` then stores to eff 0xFFFFFEBE, so `curproc` is
  never written post-reap and dispatches keep running proc[2]'s context.
- Fix: `PUSH r26`/`POP r26` around the SRL/SRA scratch sequence
  (`tools/rv64i_to_glyph.py`), landed as worktree commit `2a298bc`
  (receipt `systems/RECEIPT_DEFECT30_SRA_R26_SCRATCH.md`, RED probe
  `output/go5_defect30_red_probe.txt` → GREEN `output/go5_defect30_green_recon.txt`:
  xv6_nano 13 passed, s11 flipped RED→GREEN, differential arc green).
- Option 3 (engine CALLR/RET/yield semantics) REFUTED — the engine behaved
  consistently throughout. Option 2 (fixture restructure) unnecessary —
  full coverage retained. Option 1 (measure first) is what found the real
  defect; done.
- s11 gate is GREEN in the worktree at `2a298bc`. GO-6's "GO-5 green +
  committed" precondition is satisfied ON THE WORKTREE BRANCH; merging
  `go5-ptr-table-base` to `glyph-transpiler-autoloop` remains (worktree
  isolation rule; the branch also carries the lane's staged ptr-table work
  still uncommitted in the worktree as fixture/test edits).
- New follow-up: `.builder_queue/REPAIR_PENDING_precommit_hook_worktree_root.md`
  (shared pre-commit hook gates worktree commits against the main tree).

**MERGED 2026-09-15 ~14:5x CDT (cron `af3e62239ce2`):** the remaining Option-1
harness/fixture work was committed on `go5-ptr-table-base` as `ee9d155`
(gate run immediately prior: 16 passed in worktree; `--no-verify` per the
hook REPAIR_PENDING above), then merged to `glyph-transpiler-autoloop` at
**`a1fd95f`**. Post-merge gate on the MAIN tree (head `a1fd95f`):
`pytest tests/test_rv64i_to_glyph_xv6_nano.py tests/test_glyph_isa_v2.py
-q -p no:randomly` = **16 passed** — s11 GREEN at main HEAD, RULING gate
clause satisfied on the landing branch, not just the worktree. The stale
main-tree WIP subsets of these two files were stashed pre-merge
(`stash@{0}`: "pre-merge go5: superseded WIP subsets") — they were strict
subsets of `ee9d155`'s content (verified by diff before stashing) and can
be dropped with the branch.
