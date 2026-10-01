# RESEARCH — LD fence read gap: the GO-2 tile fence guards stores only; USER tasks read all of RAM silently

**Tick:** 2026-09-27, Phase 1c research (builder af3e62239ce2)
**HEAD at measurement:** b2c00b68 (tracked tree clean; probe untracked)
**Question:** item-29 landed per-process spatial containment (spawn tiles +
E-K1 store trap). Its own receipt carried an unverified honesty note
(`RECEIPT_item29_containment.md:66`: "LD is NOT box-checked (write-only
isolation)"). Is that gap real, silent, and does it break the containment
model a tile is supposed to provide?

## Method

- Probe `.builder_queue/probe_ld_fence_af3e.py` (untracked, landed modules
  only, zero tree mutation). Signal command to re-derive:
  `python3 .builder_queue/probe_ld_fence_af3e.py` (prints 3 runs × 3 cases
  + determinism flag).
- Harness = the landed item-29 containment path itself:
  `GlyphProcessTable.spawn(tile=(5,0,2,4))` → `arm_tile` + default reaper
  (`tools/glyph_process.py:109-176`, `tools/glyph_containment.py:74-96`).
- Three cases, each a 5-instruction program: (1) `ld_cross_fence` — USER
  LD from word 164 (first word OUTSIDE the tile) seeded with canary
  0x0BADF00D, ST the loaded value to in-tile word 160, HALT;
  (2) `st_cross_fence` — control, ST to word 164 (the B3 trap baseline);
  (3) `ld_in_tile` — control, LD/ST entirely in-tile.

## Findings (measured, deterministic across 3 runs — diff clean)

1. **`ld_cross_fence`: SILENT CROSS-FENCE READ.** rc=EXIT_OK,
   faulted=False, mode stays USER (1), in-tile word 160 ==
   195948557 == 0x0BADF00D — the exact out-of-tile canary. The task read
   across its containment fence and exfiltrated the value through an
   in-tile store, exiting clean. No fault register touched.
2. **`st_cross_fence`: trapped**, on the identical boundary word:
   rc=EXIT_FAULT, faulted=True, fault_addr=656 == 164×4, mode dropped to
   SUPER (0). The asymmetry is live on the same tree, same tile, same
   address.
3. **`ld_in_tile`: 0 lands as expected** (empty seed word) — LD itself is
   functional; the gap is purely the missing fence consult.
4. **Structural root cause (read, path:line):** the tile predicate
   `_addr_in_box` (`tools/glyph_isa_v2.py:720-747`) is consulted at
   exactly ONE site — the USER store trap
   (`:1041`, E-K1). The LD arm (`:826-909`) has no box/tile check on any
   path: unpaged RAM read `:918-919`, FS-pixel window `:915-916`, paged
   RAM target `:904-909` all read unguarded. An LD of a neighbor task's
   tile, kernel data words, or the FS window returns the live value.
5. **WGSL twin has the same gap (parity, not a backstop):**
   `walk_ld` (`tools/wgsl_glyph_isa_v2.py:351-367`) reads `ram[addr]` for
   any addr with no tile consult, while `walk_st` routes out-of-box USER
   stores through the E-K1 drop. NOT probed on-device this tick (no wgpu
   leg run); the claim is from source read of the landed shader, cited as
   such.
6. **Why it matters (fenced speculation, not load-bearing):** the tile
   fence currently provides write-isolation only; any confine-and-read
   story (agent sandboxing, per-process secrets, kernel-data privacy) is
   unsupported. Concretely: a tiled task can read the reaper/KFAULT
   words, another task's tile, or FS-window data and PRT it out.
7. **Disclosure (prior art):** the gap was DISCLOSED, not discovered
   here — `RECEIPT_item29_containment.md:66` names it and the
   glyph_process.py:119-125 docstring says "traps any out-of-tile user
   store" (accurate, store-scoped). This tick's contribution is the
   MEASUREMENT (silent-clean exfil leg + boundary control + root-cause
   sites + twin parity), which the receipt did not contain.

## Numbers policy (rule 6)

All cited numbers are structural (word values, exit codes, fault_addr,
line numbers) — no rates, latencies, or ratios, so rule-1 floors do not
attach. Signal commands named: probe run above;
`grep -n "_addr_in_box" tools/glyph_isa_v2.py` → 2 hits (:720 def,
:1041 sole call site); `grep -n "walk_ld" tools/wgsl_glyph_isa_v2.py` →
:351.

## Candidate backlog item (BK-38, filed to systems/GLYPH_BACKLOG.md)

LD tile-fence guard: in USER mode with TILE_H != 0, an LD whose address
falls outside the armed tile traps through the existing E-K1/KFAULT_PC
path (same as ST), read abandoned (rd untouched), instead of returning
the word. Gate `tests/test_bk38_ld_fence.py` with RED-first legs per the
backlog row. NOT landed by this receipt — research proposes, never lands
engine code.
