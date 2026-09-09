# RECEIPT_GH20_FS_V2 — Pixel-FS v2 (GH-20) implementation
**Ticket:** gh20-spec-finalize | **Date:** 2026-09-09 | **Branch:** glyph-transpiler-autoloop

## Symptom chain
The committed RED gate (tests/test_gh20_fs_v2.py, 5 legs) failed with
`E_ATLAS_INJECT: on-die dispatch diverged: result word 0 != expected,
exit_a 0x0, status 0x0` — the admitting task never completed after the
tile was lit.

## Root causes (3, each with a probe receipt)

### D1 — vpn-4 PTE written after pt_base armed (baker.py)
The fs_v2 prologue wrote the FS-window PTE (vpn4 -> pfn4 PTE_PIX) in a
block AFTER the `ST PAGE_TABLE_WORD <- PAGE_TABLE_BASE_WORD` arming store.
Once pt_base is armed, every subsequent ST (including to the page-table
region itself) WALKS the live table: the vpn-4 PTE store translated
vpn6->pfn5->PIXEL and never landed in RAM (probe22: on-die PTE vpn4 =
identity 0x407, vpn6 = 0x50f correct). The tile's `LD [1027]` therefore
read ZEROED RAM, every FS op took its skip branch, and admit diverged.
**Fix:** vpn4 PIX-identity is set inside the pre-arming 8-iteration PTE
loop (same shape as the vpn6->pfn5 table mapping); the dead post-arming
block removed.

### D2 — mode-dependent tile-rect coords hardcoded to "admit" (autoatlas.py)
admit_syscall called `_gh18_tile_pc(mode="admit")` and
`_gh18_dispatch_resume(mode="admit")` unconditionally. The fs_v2 task leg
is longer than admit's, shifting :__g18tile from 0x1e0007 (row 30) to
0x230006 (row 35, flat pixels [1144,1240)) (probe23; final value proven
by the leg-5 stray census landing exactly on [1144,1240) — an earlier
draft of this receipt cited probe23's 0x220005/row 34, a stale
mid-debug read). Admitting into an fs_v2 image stamped tile
words over live kernel text at row 30 and lit the table slot with a PC
pointing INTO the prologue's PTE immediates.
**Fix:** img_mode = "fs_v2" if abi == "gh20" else "admit"; both helpers
now take img_mode.

### D3 — jump relocation used baseline coords (baker._gh18_relocate_jumps)
The helper resolved the tile rect's standalone-assembly base from
_gh18_kernel_program_text() — BASELINE mode. In-tile JZ/JMP targets were
relocated ~80 cells short of the fs_v2 stamped body: the tile's
`JZ :skip` jumped into task-A's probe cells (212..217) and the dispatcher
looped forever (probe24/probe25: tile visited every pass, r5 stuck at 4,
mem754 never written).
**Fix:** _gh18_relocate_jumps(glyph_text, words, mode=...) — mode passed
through autoatlas's wrapper; admit_syscall passes img_mode.

## Also fixed in passing
- admit_syscall called ingest() TWICE (first result silently discarded);
  halved the Ollama drafting cost per admission.
- gh20 verify drive status check expected 0xCAFE0000|24 (the GH-18 admit
  tail) but the fs_v2 image writes 0xCAFE0014 (status id 20).

## Mechanical proof (pre-Ollama, monkeypatched escalate)
output/debug_gh20_probe11b.py: boot 0xcafe0014 clean; SYS 10/11/12 all
admit ok=True with table_word=0x230006 after D2+D3.

## Final gate evidence (2026-09-09, builder session)
- RED: output/gh20_gate_run5_red.txt — leg 5 failed pre-fix: 55 strays at
  [1144,1240) (the fs_v2 tile rect) against a whitelist pinned to the
  ADMIT-mode rect GH18_TILE_WORD=1600. Fix: derive the rect from the
  mode-correct packed PC (_gh18_tile_pc(mode="fs_v2") → 0x230006 →
  trow*w + tcol*4 .. +96), same mode contract legs 1-4 already pin.
- GREEN: output/gh20_gate_run5_green.txt — 5 passed in 43.06s, exit 0.
- Invariant: output/run_gate_gh18.sh (GH-18 ABI gate) 14 passed, exit 0
  at HEAD (baseline re-verified with the WIP stashed — count was 13/13
  at ticket-write time; a 14th leg landed since, both green).

## Gate
tests/test_gh20_fs_v2.py — skips lifted; result recorded in
output/gh20_gate_run.txt (see run log below).
