# RECEIPT — BK-7: FS grow (SYS 9 append) + hole reuse

**Date:** 2026-09-11
**Roadmap row:** BK-7 (systems/GLYPH_SELF_HOSTING_ROADMAP.md) — "FS grow: SYS append + file resize with FSTAB compaction (moves blocks, updates start/len)"
**Gate:** `tests/test_bk7_fs_grow.py` — RED `output/bk7_gate_run1_red.txt` → GREEN `output/bk7_gate_run2_green.txt`
**Arc regression:** GH-1..GH-26 core + BK-3/BK-4/BK-6/BK-7: **148 passed, 0 failed** in 127.74s (`output/bk7_arc_regress_v.txt`)

## Provenance / takeover note

Item was promoted from GLYPH_BACKLOG at `b4bfd27` by a prior builder run. A
parallel session left an untracked gate test + a partial, stalled WIP edit in
`tools/glyph_gpt/baker.py` (idle ~15 min, no live process). This run took over
the WIP under the BK-3 precedent: fixed it, drove the gate green, committed.

## What landed

1. **SYS 9 (append)** — `_fs_syscall_handler(n=9)` in `baker.py`:
   - ABI: a0 = file name, a1 = byte count; the task stages the next payload
     word in `scratch[736]` before each SWI.
   - Kernel reads `slot0.len`, computes the word cursor
     `old_len/4` (SHR by **2 bits** — the ISA's shift count register is BITS,
     not words; the stalled WIP shifted by 4 → `slot0.len` came out 5228),
     stores the staged word at `data + old_len/4`, then rewrites
     `slot0.len = old_len + a1` and returns the new byte count.
   - Compaction contract: start unchanged (extent grows in place in the data
     region's slack), len updated per grow.
2. **SYS 7 (read) grows up** — the slot-0 hit slice previously copied a
   hardcoded 2 words. It now reads `slot0.len`, derives the word count, and
   runs a copy loop (data cursor r10 / readout cursor r14) into the read-out
   window, returning the whole file's byte length. Non-grown (8-byte) reads
   are unchanged in behavior, so GH-8 semantics are preserved.
3. **Task A append leg** (`append_leg=True`): after the GH-8 create+write,
   two SYS 9 SWIs append `0x99AABBCC` and `0xDDEEFF10` (len 8→12→16), then
   restore `r17=6` so the packed exit word stays `0xFEED0006`
   (Bug: first green run failed `EXIT_A == 0xFEED0009` — a7 leaked into the
   exit-word packing).
4. **Hole reuse leg** (`hole_leg=True`): task B deletes 'DATA' then
   re-creates it; the create idempotence guard clears on `in_use=0`, so the
   freed slot 0 is re-claimed with `start = data region` — no FS changes
   needed (fell out of the GH-8b guard, as the WIP comment predicted).

## Bugs found & fixed on the way to green

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 14 | RED: `slot0.len = 5228 != 16` | WIP's `SHR r9 r4` with r4=4 shifted by 4 **bits** (÷16, not ÷4); the "undo" SHL then operated on a data address | Rewrote SYS 9: SHR by 2 bits for the word cursor, re-read old_len for the length update, one word per SWI |
| 15 | `EXIT_A = 0xFEED0009 != 0xFEED0006` | append SWIs left a7 (r17) = 9; exit word packs `\|r17` | `LDI r17 6` after the last append SWI |
| 16 | readout word 2 = 0 | SYS 7 slot-0 slice hardcoded 2-word copy | len-driven copy loop (see 2 above) |

## Gate legs

- **L1** `test_bk7_two_appends_grow_file_and_read_back`: create+write 8B,
  append 4+4 → FSTAB `len` 8→12→16, data region holds all 4 payload words,
  task B's whole-file read-back lands all 4 words byte-exact in the readout
  window, result = 16, exit words + kernel status `0xCAFE0008` clean.
- **L2** `test_bk7_delete_creates_reusable_slot`: delete frees slot 0;
  fresh create re-claims it (name/in_use/start restored), kernel status OK.

## Notes for future runs

- The read-copy loop is generic; slot-1 read slice still copies a fixed 2
  words from `data+2` (GH-8's second fixture file). Growing slot-1 files is
  NOT supported — fine for the current fixtures, flagged here for honesty.
- Shift semantics reminder: `SHL/SHR rd, rs` shift by `rs` **bits** (Python
  engine masks `& 31`; WGSL does not mask — small counts only, matches arc
  usage). This bit us once already; the WIP bug above is the second instance.
