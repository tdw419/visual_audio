# RECEIPT — Claim-queue round-3 item 7: Pillar 3 (d) exemption-machinery deletion

Builder: af3e62239ce2 · 2026-09-22 ~15:3x CDT · branch glyph-transpiler-autoloop
Item: delete the retired RAM-vs-pixel-space static-check machinery per the (A)
ruling's completion terms (GLYPH_ISA_ROADMAP.md:177-179: "get deleted, not
just narrowed").

## What landed (one commit)

- tools/glyph_isa_v2.py (assemble): DELETED — `IMAGE_SPACE_WRITE_SYSCALLS`
  (was {0x11: 1}), `known_reg_const` / `image_space_writes` /
  `ram_space_writes` LDI-const tracking, the GH-8b FS-window exemption
  (`in_fs_window`), and the assemble-time "RAM-vs-pixel-space mismatch"
  ValueError. Replacement comment records the retirement and the residual
  hazard (0x11-only-written addresses now assemble clean and read stale RAM
  at runtime — out of contract per DEFECT-27).
- glyph_dispatch/src/glyph/glyph_isa_v2.py: md5-identical re-sync
  (f11e02759302793d77dccebd0fb2e3a4 both sides; pre-commit hook's cmp also
  enforces this at commit time).
- tests/test_glyph_ram_pixel_space_check.py: REWRITTEN as the retirement's
  standing gate (8 legs → 6). The old suite asserted the check FIRES; the
  new suite asserts it STAYS DEAD — a revert of the deletion turns r1/r4 RED.

## Gate evidence (real exits, RED first)

RED leg (deletion applied to engine, old suite still on disk):
`2 failed, 6 passed` — test_l1 (expected the raise; now clean) +
test_l6 (non-vacuity anchor stale). The suite noticed the deletion.

GREEN (new suite, post-deletion):
`tests/test_glyph_ram_pixel_space_check.py tests/test_defect_d_ram_scoped_handlers.py`
→ `37 passed in 0.90s` (6 retirement legs + 31 defect_d, unchanged).

New-suite leg map (all _assemble/exec based, deterministic):
- r1: old L1 program (0x11 write then LD) assembles CLEAN — resurrecting
  the raise without rewriting this suite is caught.
- r2: old FS-window-exempt program still clean (window absence ≠ invalid).
- r3: pure-RAM round-trip still clean (old L2 coverage kept).
- r4: machinery names ABSENT from assembler source (deletion, not flag
  flip) AND `fs_pix_enabled` still PRESENT (the runtime mechanism was not
  swept up). Discriminating both ways.
- r5: suite non-vacuity — assembler's retained static check (SE023 jump
  bounds) still fires on an out-of-bounds JMP.
- r6: runtime GH-8b FS-window aliasing round-trip via _mem_write/_mem_read
  (write-through mirror + pixel packing bits 23..0 / 31..24) — pins that
  the live mechanism is unchanged.

## Regression (batched; full-tree pytest OOMs on this host as recorded)

- Lane family: ram_pixel_space + defect_d + glyph_isa_v2 + se025 +
  wgsl_triple_sync + glyph_on_glyph + pillar21 rotguard → 86 passed.
- Transpiler differential sample (hook-gated family): rv64i_to_glyph +
  proc + switch + printf → 7 passed.
- FS-window runtime family: gh20_fs_v2 + gh17_paging + gh18_syscall_abi +
  shell_dispatch + r51 + r52 → 43 passed.
- Collection: 2107 collected = 2109 baseline − 2, exactly the mandated
  suite rewrite (8→6 legs); defect_d still 31, no unexpected drops.

## What the PASS does NOT prove

- No WGSL/shader-path claim: the WGSL twin never had this host-side static
  check (untouched; triple-sync green confirms byte-identity of the
  wgsl copies, not a behavior delta).
- r6 pins the aliasing mechanism at the _mem_write/_mem_read API level on
  THIS host; it is not a full GH-8b re-verification (that suite,
  test_gh20_fs_v2.py, also ran green — 43-pass batch above).
- The residual hazard is real but unguarded: an LD of an address written
  only by 0x11's image-space write is silent stale-RAM. DEFECT-27 places
  it out of contract; no runtime fault exists for it.
- defect_d's "below the FS window" comments (:50, :414) describe the
  RUNTIME aliasing, still live — deliberately left untouched (cosmetic
  churn would manufacture scope).
- Single-machine, CPU-oracle only; no floors/rate claims → floors and
  check_regime N/A.

## Scope discipline

`git status --short` at landing: exactly 3 in-scope files changed by this
session (tools/glyph_isa_v2.py, glyph_dispatch twin, the gate test).
Pre-existing tracked-dirty files (guest_state.json, .update_proposals.log,
.venv bins, pxc1 frame_00230.png) are environment/guest churn from other
sessions — NOT staged.
