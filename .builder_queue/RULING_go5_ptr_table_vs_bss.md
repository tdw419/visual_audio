# RULING: GO-5 SCENARIO 11 pointer-table / `.bss` collision — lane-local base override

**Date:** 2026-09-15
**Seat:** orchestrator cron `af3e62239ce2` (mechanism-class ruling, per charter)
**Answers:** `.builder_queue/REPAIR_PENDING_go5_ptr_table_vs_bss.md`
**Class:** MECHANISM (anchor unanchoring, default-preserving). NOT a global
address-map decision — see "Not licensed".

## Decision

**Option 1 — lane-local, additive `ptr_table_base` override. Adopt it.**

Give the transpile entry points an optional `ptr_table_base: int | None = None`
**byte** address. `None` ⇒ the module constant `PTR_TABLE_BASE` (0x2000), so every
existing caller is byte-identical (GH-23, bytemem, printf, switch, defect-17
goldens). The `xv6_nano` harness passes a high base (worked value: **0x6000** —
above `.bss` end 0x3000, below `BOX_MMIO_BASE` 0x8000, inside the twin's 16384-word RAM).
The GPU twin never touches the table, so it is unaffected by construction.

## Measured evidence (seat-reproduced this tick, not taken from the ticket)

- `.bss` extents, `/usr/bin/riscv64-unknown-elf-objdump -h`, `-march=rv32i -O1 -Ttext=0x0`:
  `s8 [0x1080,0x1e00)`, `s9 [0x1068,0x15d8)`, `s10 [0x1080,0x1950)` — all clear;
  **`s11 [0x1f00,0x3000)` overlaps `PTR_TABLE_BASE=0x2000`**. Collision confirmed.
- Colliding globals (`nm -n`, s11): `g_fb=0x2280`, `g_xcode=0x25c0`, `g_grid=0x2800`
  — all inside the seeded table span, so `.bss` writes overwrite live entries.
- Table span: `build_pointer_table` returns **895 dense entries** ⇒ words
  2048..2943 = bytes `[0x2000,0x2dfc)`. Emitted table base literals:
  s10 = **4** lines, s11 = **43** lines ⇒ s11 genuinely consumes the table
  (`rv64i_to_glyph.py:1189-1210`: `LDI r30 0x2000 / ADD / SHR 2 / LD r30 r30 /
  CALLR|KJMP r30`). Corrupted entry ⇒ jump to data ⇒ twin dies mid-script. The
  reported `g_xcode=[0x130038,139,0x13003d]` garbage is this corruption
  (`g_xcode=0x25c0` is table word 2416), consistent with the GPU twin's clean run.
- Feasibility: `IRContract`/`PointerTable.base_word` is already a parameter
  (`tools/glyph_ir.py:220-225`), and `RESERVED_RANGES` does not pin the table ⇒ a
  non-canonical base is expressible without touching the IR contract format.
- Why not raise the global constant: `GH23_HEAP_BASE=2560`/vpn 0..10 (words 0..2815)
  deliberately sit above the table (`tools/glyph_gpt/libc_runtime.py:45`,
  `baker.py:5207`). A base ≥ word 2815 falls outside the libc mapping window ⇒
  indirect calls fault; a base inside it re-collides with s11 `.bss`. Only
  lane-local placement satisfies both.

## Constraints the lane must honour

1. **One source of truth.** Thread the override to all consumers: emitted `LDI r30`
   literal (`tools/rv64i_to_glyph.py:1195`), `data_bounds` (`:1264`),
   `PointerTable(base_word=...)` (`:1273`), and harness seeding
   (`tests/test_rv64i_to_glyph_xv6_nano.py:208-209`). Add an assertion that the
   seeded word equals the emitted literal base; a mismatch is a silent wrong-jump bug.
2. Keep it 4-aligned; span `[base, base+3584)` must stay `< 0x8000` and inside
   `len(cpu.memory)`; must not be reachable by the downward-growing stack.
3. **Worktree isolation** (AGENTS.md blast-radius rule — this touches a core file).
4. Do not edit `tools/glyph_gpt/*` or any `GH23_*` constant.

## Gate (lane must satisfy)

```bash
/usr/bin/python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py -q -p no:randomly
```
→ **13 passed** (s11 included), plus all five clauses of
`.builder_queue/brief_go5_e2e_gpu_os.md` § Gate. Gate log must also print, for s11,
the `.bss` end, the chosen base, and the seeded table span, showing disjointness —
and must show the pre-fix run RED on that same print (discriminating, per
AGENTS.md evidence discipline). Existing callers' byte-identical output must be
shown, not asserted.

## Not licensed by this ruling

- **Any global change to `PTR_TABLE_BASE`**, and any re-derivation of the GH-23 vpn
  window / `GH23_HEAP_BASE` (ticket Option 2). That rewrites landed receipts for a
  producer nobody emits yet — **Jericho's call if ever wanted**.
- **Shrinking SCENARIO 11 `.bss` / `g_grid`** (Option 3) — fixture-behaviour change.
- Deleting, skipping, or weakening any test; changing the 20ms symbol constraint;
  touching `voicebook/`, `.rts/`, `rs_fixtures.json`.
- **Greenness beyond the collision.** If s11 still diverges after the override,
  this ruling does not cover it: the residual (per
  `REPAIR_PENDING_go5_scenario11_engine_divergence.md`, suspected console
  byte-vs-word write granularity) must be measured to the responsible store
  instruction and filed as its own ticket. Do not paper over it or re-open this base.

## Disposition

Ticket answered; lane may implement Option 1 under worktree isolation and the gate above.
