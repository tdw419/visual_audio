# RESEARCH — PARALLEL_ST fence bypass: a tiled USER task can write (and
# re-arm) any RAM word, including the fence's own config, with a clean exit

**Tick:** 2026-09-27, Phase 1c research (builder af3e62239ce2)
**HEAD at measurement:** bf6f2b6e (tracked tree clean; probes untracked)
**Question:** BK-38 measured the read gap (LD unguarded). The write side
was assumed fenced because `_addr_in_box` fires at the ST trap
(`glyph_isa_v2.py:1041`). But ST is not the only guest-reachable WRITE
arm: PARALLEL_ST writes `self.memory[a]` directly (`:1271-1274`) with a
bounds check only — no mode check, no box consult — and PUSH/CALL write
the IMAGE plane via `_mem_write` (`:702-708`, `:1091-1105`) with no box
consult either. Is the write fence bypassable by the sibling write arms?

## Method

- Probes `.builder_queue/probe_pst_fence_af3e.py`,
  `probe_pst_disarm_af3e.py`, `probe_pst_escalation_af3e.py`,
  `probe_push_mechanics_af3e.py` (untracked, landed modules only, zero
  tree mutation). Signal command:
  `python3 .builder_queue/probe_pst_escalation_af3e.py`.
- Harness = the landed item-29 containment path itself:
  `GlyphProcessTable.spawn(tile=(5,0,2,4))` (rows 5-6, cols 0-3; word
  164 = row 5 col 4 = first word OUTSIDE the tile).
- Determinism: the escalation probe's output file is byte-identical
  across 3 runs (md5 d527708d67897cab2521fda20f40a982, measured); the
  boundary probe prints `deterministic: True` across 3 internal runs.
- Probe-hygiene disclosure: the boundary probe's first draft seeded the
  TILE_H config word to 0 post-spawn, DISARMING the fence under its own
  controls; caught on read-back (control `st_cross_fence` still trapped
  via the BOX ranges, masking it) and fixed before any finding was
  recorded. Final runs show `tile_h_word: 2` in all 12 case prints.

## Findings (measured, deterministic across 3 runs)

1. **`PARALLEL_ST` is a silent cross-fence WRITE.** From the tiled USER
   task: `LDI r2 164; LDI r3 <canary>; PARALLEL_ST r2 r3 1; HALT` →
   rc=EXIT_OK, faulted=False, mode stays USER, `memory[164] ==
   0x0ADF00D` (the canary landed out-of-tile). The plain-ST control on
   the SAME word traps (rc=EXIT_FAULT, fault_addr=656, mode→SUPER) on
   the same tree, same tile, same address. The in-tile PARALLEL_ST
   control lands normally — the opcode works; the gap is the missing
   consult (root cause: `glyph_isa_v2.py:1264-1295` — bounds check
   `:1273` only; zero calls to `_addr_in_box` on any path).
2. **FULL ESCALATION — a tiled USER task can self-grant the box.**
   `PARALLEL_ST` can write the isolation MMIO block itself: the task
   sets `BOX0_LO := 0` and `BOX0_HI := 65536` (words 8195/8196) from
   INSIDE its tile, then plain-`ST`s to word 999 — clean exit, value
   4660 lands, faulted=False. The fence is not merely bypassable; a
   confined task can REWRITE ITS OWN CONFINEMENT to cover all of RAM
   using the one write arm the fence never checks. Also measured: the
   same arm disarms the tile (`TILE_H := 0`, word 8282) or re-anchors it
   (`TILE_ROW := 0`) — in both cases the SUBSEQUENT plain ST still
   traps (fault_addr 3996 / 160), because `_addr_in_box` reads the tile
   words live but the E-K1 ST arm reads them at store time; only the
   BOX0 self-grant produces a clean out-of-fence store.
3. **`PARALLEL_LD` has the read-side gap too.** `PARALLEL_LD r4 <164+4>
   1` from the tiled USER task returns the out-of-tile canary
   (r4 == 0x00ADF00D, clean exit) — the BK-38 read gap extends to the
   parallel read arm (`:1250-1262`, no box consult).
4. **PUSH/CALL write the IMAGE plane, not the Word-RAM, with no box
   consult.** `PUSH` pre-decrements r31 and `_mem_write`s the image
   pixel (`_addr_to_xy` scanline: word 164 → pixel (4,5) on a 32px-wide
   image). Measured: a tiled USER task PUSHes to word 164, POP round-
   trip returns 12345, the image pixel at (4,5) == (0,48,57) ==
   0x003039 — an out-of-tile image-plane write, clean exit, mode stays
   USER (`probe_push_mechanics_af3e.py`). Caveat: the image plane is a
   different address space from the task's own RAM (this program image
   is 31 rows and the tile words govern the RAM grid), so the
   blast-radius of THIS leg is instruction-stream corruption of whatever
   program lives at that pixel, not RAM disclosure. The PST leg is the
   load-bearing one.
5. **Structural root cause (read, path:line):** the E-K1 tile/box
   predicate is consulted at exactly ONE execute site — the ST arm
   (`:1041`). The PARALLEL arms (`:1250-1262` LD, `:1264-1295` ST) and
   the stack/call arms (`PUSH :1091`, `POP :1094`, `CALL :1101-1105`)
   go straight to RAM/image with no mode-or-box consult. The WGSL twin
   is NOT exposed the same way BY SOURCE READ: `_OPCODE_ORDER`
   (`wgsl_glyph_isa_v2.py:34-39`) does not include the PARALLEL opcodes
   at all (a GPU program containing them halts ENG-1 unknown-opcode),
   and `walk_st` DOES check `addr_in_box` (`:451`). Not probed
   on-device this tick (no wgpu leg); cited as source-read only.
6. **Why it matters:** item-29's containment story ("the engine's
   existing box check then traps any out-of-tile user store",
   `tools/glyph_process.py:122-123`) is overstated by one opcode class.
   The blast radius is not just reads (BK-38) or stray writes: the BOX0
   self-grant makes the fence a policy the confined task can edit.
   Every layer built on tile containment (items 26/29/34/35/38 guest
   isolation claims) inherits this.
7. **Prior art:** the PARALLEL arms predate item-29 (GH-9 loader era,
   per the `:1275-1290` comment) and item-29's receipt scoped the fence
   to the ST path; neither names the sibling arms. This tick's
   contribution: the measurement of the bypass AND the self-grant
   escalation.

## Numbers policy (rule 6)

All cited numbers are structural (word values, exit codes, fault_addr,
line numbers, pixel tuples, an md5 of a probe output file) — no rates,
latencies, or ratios, so rule-1 floors do not attach. Signal commands
named above; re-derive in one command each:
`python3 .builder_queue/probe_pst_escalation_af3e.py`;
`grep -n "_addr_in_box" tools/glyph_isa_v2.py` → 2 hits (:720 def,
:1041 sole call site); `grep -c PARALLEL tools/wgsl_glyph_isa_v2.py` → 0.

## Candidate backlog item (BK-39, filed to systems/GLYPH_BACKLOG.md)

Fence-all-write-arms: route PARALLEL_ST (and PUSH/POP/CALL image-plane
writes, at minimum for the RAM-grid portion) through the same USER+tile
consult as ST, AND make the box/tile config words kernel-write-only from
USER mode (no guest-reachable arm may write BOX*/TILE* words; trap loud).
Gate `tests/test_bk39_write_fence.py` with RED-first legs per the
backlog row. NOT landed by this receipt — research proposes, never
lands engine code.

## What this receipt does NOT prove

- No WGSL on-device run (twin claims are source-read).
- No claim that any landed gate/fixture currently RELIES on the
  PARALLEL_ST bypass (the BK-39 family leg must check at landing time).
- PUSH/POP/CALL legs are measured on the image plane only; RAM-side
  effects of POP (read arm) were not separately probed beyond the
  PARALLEL_LD leg.
