# RESEARCH — DEFECT-31e: the LANDED rs1==30/rs1==29 fix branches carry
# their own latent value-register aliasing class (8 RED legs measured)

Filed: 2026-09-26 ~0:2x CDT, builder af3e62239ce2 (Phase-1c research tick)
Question owner: backlog row BK-29 (filed this tick; NOT lane-claimable)
Revision under test: HEAD 03dd25d4 (tree == HEAD, tracked-clean at tick start)

## Question

Last tick's receipt (RESEARCH_defect31c_latent_aliasing.md) measured the
SB/SH **else branches** (rs1 != x30) and filed BK-28. It explicitly did
NOT ask: are the **fix branches themselves** — the rs1==30 (and SW's
rs1==29/30) guard sequences landed in DEFECT-31c / DEFECT-31 — free of
the same scratch-aliasing class? Reading the landed lowering, the value
register rs2 is consumed by `LDI r26 0; ADD r26 r{rs2}` AFTER r27/r28/r29
have already been used as lane/shift/word_addr/cur_word scratch. If gcc
allocates rs2 ∈ {x26,x27,x28,x29}, the fix branch should read a clobbered
value. Unmeasured. This tick measured it.

## Method (path:line, re-runnable)

Probe `.builder_queue/dbg_d31e_fixbranch_alias_af3e.py` (12 legs) +
independent single-leg recheck `.builder_queue/dbg_d31e_recheck_a2_af3e.py`
(fresh code, fresh tempdir — written specifically to guard against
harness drift). Same pipeline as the 31c probe: riscv64-unknown-elf-gcc
-march=rv32i -mabi=ilp32 -nostdlib -Ttext=0x200 → transpile
(tools/rv64i_to_glyph.py transpile_elf_to_glyph, tree AND
`git show HEAD:` snapshot — op streams byte-identical per pc in all 12
legs, so latent-at-HEAD, NOT a lane regression) → `_load_posix_program`
(tests/test_gh23_libc_runtime.py:387) → libc_runtime_kernel_image
(tools/glyph_gpt/libc_runtime.py:223) → GlyphRunner.run
(tools/glyph_gpt/runner.py:52), 20000-instruction cap, mem[] read from
the receipt. Deterministic; no GPU, no LLM, no network.

## Findings (numbers are structural asserts from runner receipts this tick)

Probe summary: **4/12 PASS, 8 RED** — every RED halts cleanly with
faulted=False (SILENT corruption, same as the 31c class).

SB/SH fix branch (tools/rv64i_to_glyph.py:1058-1083 SB, :1163-1187 SH),
rs1=x30, base 0xC00 → word 768:
- sb value x26 → mem[768]=0x0  (golden 0x42) RED
- sb value x27 → 0x0 (golden 0x43) RED
- sb value x28 → 0x0 (golden 0x44) RED
- sb value x29 → 0x0 (golden 0x45) RED
- sh value x27 → 0x0 (golden 0x4243) RED
- sb value t1 (non-aliased control) → 0x41 PASS

Mechanism, visible in the transpiled artifact itself (recheck probe
prints the listing): for `li x30,0xC00; li x27,0x43; sb x27,0(x30)` the
lowering emits `... LDI r29 2; SHR r28 r29; LD r29 r28; LDI r26 0;
ADD r26 r27; ...` — the `ADD r26 r27` reads the LANE/SHIFT SCRATCH r27,
which now holds the shift amount, not RV x27's value. The stored lane is
`value_scratch & 0xff` = 0 → whole stored word collapses to lane-clear +
0.

SW fix branch (tools/rv64i_to_glyph.py:930-952), rs1=x30:
- sw value x26 → mem[768]=0x2 (golden 0x2222) RED — `LDI r26 2` (the
  byte→word shift) destroys x26 before `ST` reads it; 0x2 is exactly the
  shift constant landing in the value lane
- sw value x28 → 0x300 (golden 0x3333) RED — r28 is the ADDRESS temp on
  this path (holds word_addr=0x300); the value read picks up the address
  itself
- sw value x29 → 0x4444 PASS (predicted: x29 is not touched on this path)
- sw x0 → word 769 zeroed PASS (the rs2==0 leg is fine)
SW rs1==x29 elif branch (:935-937):
- sw value x26, base x29 → 0x0 (golden 0x5555) RED — same r26 shift-temp
  clobber
SW non-aliased control (t1) → 0x6666 PASS.

## Candidate (backlog BK-29, filed to systems/GLYPH_BACKLOG.md:56)

SB/SH/SW fix branches: complete the value-side aliasing guard — read rs2
into a saved scratch BEFORE any lane/shift/word_addr scratch LDI (mirroring
how the else-branch BK-28 fix shape reads value first), with callee-saved
PUSH/POP around it. Gate: tests/test_defect31e_fixbranch_aliasing.py, the
8 RED probe programs as fixtures + 4 control legs, RED-first at current
HEAD, worktree isolation (engine-core transpiler) per AGENTS.md.
Touch surface: tools/rv64i_to_glyph.py:1058-1083, :930-952, :1163-1187.

## Honesty (rule 6)

- Every number above is a structural assert (mem/halted/faulted read from
  GlyphRunner receipts of real runs this tick). No rate, no latency, no
  floors claim → rule-1 floors treatment does not attach.
- "tree==HEAD byte-identical" was verified per-leg in the 12-leg probe
  (op-stream diff by pc). The independent recheck did NOT repeat the
  tree-vs-HEAD diff (single transpiler invocation); it re-derives the
  mem[768] number only.
- NOT verified: no WGSL twin leg (transpiler-side lowering, nothing
  spatial); no xv6-nano scenario currently allocates x26..x29 as a
  store VALUE into an x30/x29-based address, so all landed gates stay
  GREEN (latent-only — this is not a regression and does not flip any
  landed verdict; rule-2 does not trigger).
- Probe-echo drift disclosure: two terminal echoes this session showed
  mangled paths/identifiers (cosmetic harness-output corruption, cwd
  /home/jericho/projects/zion/projects/visual_audio unchanged); the
  load-bearing A2 number was re-derived with fresh code
  (dbg_d31e_recheck_a2_af3e.py) and matched (0x0 vs golden 0x43, RED).
- Priority signal (self-assessed, one command to re-derive):
  `git log --oneline -20 -- tools/rv64i_to_glyph.py` — 6 of the last 20
  commits are this exact aliasing defect family (DEFECT-11/16c/30/31/31c),
  and each fix so far has guarded only the branch that the then-current
  gate exercised. BK-29 is the closing move for the family.
