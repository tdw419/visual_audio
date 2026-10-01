# RULING — 2026-09-12 (orchestrator seat, under Jericho's standing "you lead")

Three decisions that unblock the loop, each grounded in measurements already in
this tree rather than in the ticket's original framing.

---

## 1. DEFECT-19 is the real blocker for BK-11 — and it is NOT a design decision

**Supersedes the DEFECT-18 framing for the leg-2 symptom.** DEFECT-18 presented
the BK-1 leg-2 red as a *tick-contract vs identity-map* design choice and asked
for (a)/(b)/(c). The 08:22 tick prototyped option (a) engine-side and measured
it, so the question is now settled by evidence, not by preference:

| configuration | `tests/test_bk1_argv.py` |
|---|---|
| HEAD + option (a) | 5/5 green (6 ticks / 6 restores) |
| held LBU patch + option (a) | **STILL RED** (7 ticks / 7 restores — every tick transparent) |

Option (a) makes ticks transparent and *still does not unblock leg 2*, because
the clobber lands at step 3084 — **448 steps before the first tick** (3532) — and
the errant value `0x8b4513` is present in the injected program's own pixel stream.

**Root cause (DEFECT-19, `3d0acc6`):** `loader_kernel_image()` writes `4*N`
program words into RAM from `dst = start_cell*4` **unbounded**, straight across
the box's own ABI words:

| variant | copy span | collides with |
|---|---|---|
| HEAD, 84 instr, q0 | [304, 640) | nothing |
| HEAD, 84 instr, q12 | [396, **732**) | one word short of `GH9_TICKS_COUNT` (732) |
| LBU, 96 instr, q0 | [304, 688) | nothing — result byte-exact `0x3b00112a` |
| LBU, 96 instr, q12 | [396, **780**) | **732 (ticks) AND 750–766 (argv/result)** |

Post-run ABI words after LBU@q12 hold program-pixel garbage
(`750:0x0 752:0x00ec5050 760:0x00ec5050 761:0xffff1d`) where HEAD@q12 is intact
(`751:0xbe0 760:0xbf0 766:0x2a11`). Widening the harness window 96→128 changes
nothing.

**RULING: the fix is a bounded copy span in the GH-9 loader.**
- Bound `loader_kernel_image()`'s RAM write so it cannot overlap the box ABI
  words (703 exit, 732 ticks, 750–752 argv header, 754 result, 760–766 argv
  data), and fail loudly if a program is too large for its window instead of
  silently overwriting the ABI.
- Add a gate leg that asserts **no ABI-word overlap** for the largest landed
  program at the tightest quantum (this is the leg that would have caught
  DEFECT-19 years of debugging earlier).
- Keep the identity map. No landed receipt is invalidated and no claim is
  retracted — which is why this needs no design sign-off.
- Re-apply the held `.builder_queue/held_patches/defect16c_lbu_lhu.patch`, then
  require **`tests/test_bk11_coreutils.py` 6/6 AND `tests/test_bk1_argv.py` 5/5
  simultaneously** — that conjunction is BK-11's definition of done.

**DEFECT-18/17 (tick scratch registers vs identity map) stay open as hardening,
not as BK-11's blocker.** Option (a) is the right eventual fix for the class
(measured: makes ticks transparent at 6/6 restores), and DEFECT-17 (RV x31/t6
lowering onto glyph r31, the hardware call stack) is latent with no landed gate
exercising it. Schedule them after BK-11 closes, as their own item with their own
gate.

---

## 2. BK-13 Q2 — the "instance boundary" is TWO KERNELS IN ONE IMAGE

The backlog clause said "two Glyph OS instances, host-mediated loopback first"
without defining the boundary. Two readings were possible; **ruled: the in-image
variant.**

- **Chosen:** two kernels inside ONE image, exchanging frames through the real
  mailbox windows, with every frame crossing the admission oracle *in-substrate*.
  The host is the runner/observer, never the transport.
- **Rejected for now:** two `GlyphRunner` processes joined by a host-side pipe —
  the untrusted host lands in the transport path, which is precisely the boundary
  this architecture exists to keep out, and it reduces "every frame crosses the
  oracle" to a host-side convention rather than a substrate property.
- Reuses proven machinery (GH-18 ABI facts, GH-22 mailbox word format,
  GH-12/18 admission), so the first gate is mechanical: A sends 64B through its
  mailbox, B receives byte-exact, a malformed frame is rejected by the oracle
  **with a receipt**, and no host I/O path exists in the data movement.

SYS numbers are already amended to **SYS 18 = net_send / SYS 19 = net_recv** in
the backlog row (`cda559b`) so this item cannot collide with BK-9's `SYS 14` or
BK-10's `SYS 16/17`.

---

## 3. Environment: worktree isolation is unblocked again

AGENTS.md requires worktree isolation for core-file changes, and the DEFECT-19
fix touches `tools/glyph_gpt/baker.py` (a fast-path core file). The 08:22 tick
reported the fix deferred because a worktree could not be created at 34 GB free
(99% full).

Freed **27 GB** by removing the stale-but-unmerged GH-19 worktree
(`.worktrees/gh19-stdlib`), which was the largest reclaimable block:

- The branch `gh19-stdlib-track` and **all** its commits survive in `.git` — the
  worktree checkout was the cost, not the history.
- Its three dirty tracked files (runtime state) were committed first as
  **`d784bcb`** so nothing was lost.
- Two untracked artifacts in it (`tests/g15.c`, `demo_glyph_program.png`) were
  verified byte-identical to copies already in the main tree before removal; the
  1.5 GB `.venv_gh19_full/` was rebuildable and is the only thing actually
  discarded.

Result: **61 GB free**. Worktrees are affordable again; the next core-file item
can isolate as the constitution requires. Remaining reclaimable if ever needed:
`.git` is 47 GB (repack in a quiet window) and the HuggingFace cache is 15 GB
(not this project's).

---

## Consequences for the loop

1. **BK-11 becomes eligible again**: apply the held patch, implement the bounded
   loader copy, land the no-ABI-overlap gate leg, and close on the 6/6 + 5/5
   conjunction.
2. **BK-13 becomes promotable** with Q1 (numbers) and Q2 (in-image boundary)
   both answered.
3. Neither ruling asks the loop to invent scope, and neither rewrites a claim —
   the two things the escape hatch exists to prevent.
