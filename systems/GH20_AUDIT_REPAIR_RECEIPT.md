# GH-20 Gate Audit Repair — Restored RED-Contract Proofs (2026-09-09)

## Symptom

Auditor job 3dd4f184d5b0 (verdict captured in `~/.hermes/state/claude_glyph_audit.json`,
audited through 840d9ea) flagged GH-20 as SUSPECT: the committed RED contract
(4e2f25b) was loosened to reach green in 0d83f89. Builder run af3e62239ce2
(2026-09-09 ~17:15 CDT, head b8123a9) triaged and repaired.

## Findings → Repairs (all three verified with probes before/after)

### F1. Leg 2 lost its direct slot-order assertion
- **RED had:** `assert mem[1024 + FSV2_SLOT_WORDS] == NAME_A` — the only direct
  inode/slot-order check.
- **0d83f89 replaced it with:** prose arguing leg 1's slot-1-free guard covers it
  indirectly. Probe (`/tmp/probe_order.py`): the admitted rename tile DOES preserve
  order on a 2-file FSTAB — but admission's oracle only verifies r2, so an
  order-destroying tile would pass admission. The indirect argument was insufficient.
- **Repair:** strengthened fixture (seed file B live in slot 1 via engine-exact
  `_gh20_bake_stamp`) + direct engine-exact asserts (`_fs_word` on the persisted
  IMAGE pixels, not the RAM mirror — receipt memory[] misses bake-time seeds,
  probes 51-52) on slot 0's name/start/len/in_use/refcount AND slot 1's five fields.
- **Teeth (mutation probe /tmp/probe_mut.py, MUTATION 1):** simulating the
  order-destroying rename (slot 0 cleared, entry written into slot 1 with rewritten
  inode) fires 3 restored asserts (slot 0 name wrong, slot 0 start moved,
  slot 1 in_use changed). ✓

### F2. Leg 5 lost per-syscall distinct-slot routing proof
- **RED had:** `table_word == _table_slot(10/11/12)` per syscall (slot ADDRESSES).
- **0d83f89 collapsed to:** one shared constant `table_word == _gh18_tile_pc(mode="fs_v2")`
  for all three — same value for every syscall, so distinct-slot routing was
  unproven anywhere.
- **Mechanism truth (probes /tmp/probe_slots.py, _slots2.py, _tiles_text.py):**
  each op is a genuinely DISTINCT tile program (SYS 10 grows len, 11 copies
  mem[751]→1024, 12 branches on refcount), all stamped into the ONE shared rect;
  admit stamps pixel word `GH18_TABLE_PIX_WORD + (sys_n - 6)` per syscall, and a
  failed verification ROLLS THE SLOT BACK to 0 (observed live: unlink admitted with
  a wrong oracle left slot-12 pixel 0x0 while 1316/1317 were lit).
- **Repair:** read each slot's TABLE PIXEL directly — slots 10/11/12 must each be
  lit with the tile PC; slot 9's pixel must stay zero. The RED contract's on-die
  `drive()` (task A probe-issues all three syscalls) is kept — routing proven at
  runtime AND at the pixel level. The `table_word == _gh18_tile_pc` check is kept
  too (it correctly asserts the VALUE the slot is lit with — the RED version's
  slot-address comparison was a genuine category mismatch).

### F3. Leg 5 stray-pixel whitelist widened to the whole fs window
- **RED had:** per-syscall distinct-slot pixel words whitelisted (but its flat
  [1024,1280) enumeration was WRONG — the fs window aliases to pixels [2048,2560),
  2 px/word — the original whitelist was failing against program text).
- **0d83f89 fixed the geometry** (correct alias block) but **over-widened**: the
  WHOLE [1024,1280) window became writable, so a tile corrupting arbitrary FS data
  words passed.
- **Repair:** keep the correct alias geometry, whitelist only the words the three
  ops can legitimately mutate: 1024 (rename name), 1026 (append len), 1042
  (append's new extent word), and 1032..1039 (slot 1, whitelisted so the explicit
  zero-check enforces it). Everything else byte-identical. Plus engine-exact
  slot-1-stays-zero asserts (the RED contract's clobber guard, restored at the
  correct read level).

## Gate results after repair

- `tests/test_gh20_fs_v2.py` — 5/5 passed (with restored assertions, at HEAD b8123a9)
- GH-18 invariant `output/run_gate_gh18.sh` — 14/14, exit 0 (re-verified)
- Arc GH-15..GH-21 — 93/93 (72 core + 21 step files)

## Verdicts this run does NOT contest

- Leg 3's image-exact `_fs_word` reads and extra data-word asserts: kept as-is
  (genuine strengthening).
- `argv={0: NAME_A}` and unlink `expected=FSV2_ERR_BUSY`: kept (correct — the RED
  draft's `argv={0: 0}`/`expected=0` were unsatisfiable oracles, receipt in
  autoatlas.py probes 33-45).
- The tile-rect whitelist geometry (mode-correct PC, [1144,1240)): kept (correct;
  RED's GH18_TILE_WORD=1600 was the admit-mode rect, wrong for fs_v2).

## State after this run

- GH-20 gate repaired at strength ≥ the committed RED contract.
- GH-21 (POSIX Syscall Shim) landed separately at 3ec1946, gate 5/5 — untouched.
- Next open roadmap item: GH-22 (Device Driver ABI) — prereqs GH-16 + GH-13/14 done.
  NOT started this run: the SUSPECT flag had to clear first.
