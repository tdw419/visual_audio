# RECEIPT — SE021 claim-queue item 2, step: 0x10 BOOT_LINUX header PIXEL→RAM (backlog (d) residual)

**Builder:** cron af3e62239ce2 · 2026-09-22 · branch glyph-transpiler-autoloop
**Rung authority:** PRODUCT_LANE_STATE.md CLAIM QUEUE item 2 (RULED "(A) scoped
to handlers", 2026-09-16; RELEASED by measurement 2026-09-18,
RULING_SE021_release_by_measurement_20260918.md). Spec read first:
systems/SCOPING_MEMORY_VIEW_UNIFICATION.md + GLYPH_ISA_ROADMAP/ROADMAP.md
TASK_SE021 row (ROADMAP.md:1790-1791).

## What was found (reports vs machine)

- Backlog (d) was declared COMPLETE 5/5 on 2026-09-16
  (TICKET_SUPPLY_STATE_ADDENDUM109.md) — but that ledger's 5 handlers were
  0x01/0x03/0x04/0x08/0x09. The scoping §2 inventory lists 0x10's container
  header as image-space too; nothing forced the question in September because
  0x10's fixtures seed via `cpu._mem_write` (image) and nobody re-read the
  scoping doc against the sweep's own scope line ("data/dest args").
- **Env repair (pre-existing RED, fixed first):** the standing gate
  `tests/test_defect_d_ram_scoped_handlers.py` was 8 FAILED /
  ModuleNotFoundError at HEAD — scipy + soundfile (then mcp<2, librosa) were
  missing from the repo .venv, lost in the 2026-09-19 ENOSPC cache cleanup.
  This also retro-fixes the "8 defect_d audio failures" the R1.4 session log
  attributed to the env. After reinstall: 25 passed.

## What landed (one commit)

1. **tools/glyph_isa_v2.py** — 0x10 arm reads its VAC2 header from
   `self.memory` (RAM), one byte per word low-byte-first (the (d) data
   convention), out-of-range words read 0 → signature fails → -1, never
   IndexError. Image is no longer consulted.
2. **WGSL twin (both engines rule)** — tools/wgsl_glyph_isa_v2.py gains a
   legacy-table `syscall_num == 16u` branch: `ram_read` per byte, accept iff
   `VAC2`, else -1 (u32 0xFFFFFFFF). ram_read does NOT fall back to image
   pixels, so image-only seeding is refused — matching the CPU. Triple-sync
   copies re-synced (tools/, glyph_dispatch/src/glyph/,
   glyph_dispatch/src/ — the sync gate names the third path).
3. **docs/SYSCALL_ABI_SPEC.md** — 0x10 entry: storage PIXEL→RAM, twin
   BRIDGED→IMPLEMENTED, byte layout rewritten. The doc-rot guard
   (test_pillar21_abi_spec_rotguard.py L2/L3) caught the stale doc the
   moment the engine moved — that is the guard working, recorded as such.
4. **tests/test_defect_d_ram_scoped_handlers.py** — +7 legs (25→32):
   historical (old pixel-packing replay), post-migration RAM recognition,
   image-signature-refused mirror, out-of-range no-crash, non-vacuity
   neuter (swaps read+sig-assembly back to the old body, proves the mirror
   leg flips), WGSL parity (real GPU: RAM-seeded → 0, image-only → -1).
5. **tests/test_syscall_handlers.py** — 2 fixtures re-staged image→RAM
   seeding (payload/weights metadata moved to RAM words too), RAM widened
   to 16384 (0x1000 exceeds default 1024; no auto-growth).
6. **tests/test_pillar21_abi_spec_rotguard.py** — L4 0x10 leg updated to
   the new spec claims (RAM / IMPLEMENTED); L2/L3 pass unmodified once the
   doc was truthful.

## RED → GREEN (pasted from real runs)

RED (engine un-migrated, `-k 0x10`):
```
4 failed, 2 passed, 25 deselected in 0.83s
FAILED tests/test_defect_d_ram_scoped_handlers.py::test_0x10_boot_linux_reads_ram_not_image
FAILED tests/test_defect_d_ram_scoped_handlers.py::test_0x10_boot_linux_image_signature_alone_is_not_recognized
FAILED tests/test_defect_d_ram_scoped_handlers.py::test_non_vacuity_neutered_0x10_fix_reads_image_again
FAILED tests/test_defect_d_ram_scoped_handlers.py::test_0x10_boot_linux_wgsl_parity
```
Landing-time defects kept (caught by the gate before any green):
the seeding helper initially kept the OLD 2-bytes-per-pixel packing
(sig read b'V2\x00\x00'), and the neuter probe only swapped read lines,
not the sig assembly. Both were TEST defects; engine right, tests fixed.
GREEN (full gate):
```
31 passed in 0.90s   (tests/test_defect_d_ram_scoped_handlers.py)
45 passed            (handlers + integration + defect_d + oracle)
20 passed            (pillar21 abi-spec rotguard)
```

## Regression sweep (batched; full-tree run OOM-killed 3x at ~62%)

- Lane-family suites: 104 passed (syscall/conformance/glyph_cc/glyph_run/
  r52/WGSL parity family, 11.89s) + 65 (SE021 family incl. rotguard).
- Full tests/ (batched into eighths): batches aa/ab/c/d: 13 failed (aa),
  10 failed (ab) — **every one reproduced at HEAD with the lane diff
  stashed** (13 failed / 25 passed on the exact same file set): go6
  disk-word, nested_buffer dtype, cross_lingual SystemExit, bk11 coreutils,
  dct scipy, agy_wrapper reversed-patch, gh23 libc, gh24_s2 (order
  pollution only — 6/6 in isolation). NOT this diff.
- 3 collection errors (defect20/gh26_glass_box/obs1) pass individually;
  cross-module pollution under full collection, pre-existing (cf. R2.1
  ledger note: 39 pre-existing collection errors).

## What this PASS does NOT prove

- **View-merge retirement NOT done** — `_read_path` (glyph_isa_v2.py:1374)
  still view-merges image fallback. Scoping §7 lists it in the
  recommendation; it is a separate gate-able step with its own blast radius
  (fixtures seed paths image-side, e.g. test_run_containment). Next step of
  claim-queue item 2, not silently dropped.
- WGSL parity proven on the legacy-table path (no dispatcher armed) — the
  E-K2 armed-dispatcher path is unchanged by this diff.
- 0x10 remains recognition-only (no boot); PNG-persistence coherence now
  rests on the FS window as before — no change to the 256-word I/O budget.
- Full-tree single-process pytest is currently NOT runnable on this host
  (OOM); batched sweep is the evidence, with the stashed-diff A/B above.
- No rate claims → floors/check_regime N/A.
