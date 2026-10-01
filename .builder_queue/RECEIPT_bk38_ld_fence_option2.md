# RECEIPT — BK-38 / BK-56: Scoped GO-2 Tile LD Confinement & MMIO Read Posture (Option 2 Refined)

**Trigger:** `RULING_BK38_READ_POSTURE.md` binding on `bk38-45-sequenced-fence-commit` (worktree `va_fence_worktree`).
**Decision:** Option 2 refined — scope LD confinement to the GO-2 tile boundary; close the measured attack surface via MMIO read posture, NOT general LD confinement.
**Date:** 2026-09-27.

## What landed

- `tools/glyph_isa_v2.py`:
  - `GlyphCPUv2._tile_confinement = False` initialized in `__init__`.
  - In `step` opcode `'LD'`:
    - `elif self.mode == MODE_USER and self._tile_confinement:` traps out-of-tile reads to E-K1 (records `fault_addr`/`fault_pc`, drops to SUPER, vectors to `KFAULT_PC`).
    - `elif self.mode == MODE_USER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256:` returns 0 for USER reads of MMIO config words (BK-56 oracle parity).
    - General USER LD outside the tile confinement remains unfenced for cooperative single-address-space kernels (xv6-nano).
- `tools/glyph_process.py`:
  - In `GlyphProcessTable.spawn(..., tile=...)`: sets `cpu._tile_confinement = True` when `tile is not None`.
- `tools/wgsl_glyph_isa_v2.py`:
  - In `walk_ld`: gates `box_mmio` read with `if (!is_super) { return 0u; }` (BK-56 WGSL parity).
- `tests/test_bk38_ld_fence.py`:
  - 6-leg verification gate (L1..L4 plus F1 and F2 falsifiers).

## Verification Gates & Falsifiers

All 19 test legs passed green in 41.91s (`pytest -q tests/test_bk38_ld_fence.py tests/test_rv64i_to_glyph_xv6_nano.py`):

1. **F1 (MMIO config block read posture):**
   - With MMIO read posture live, USER LD of word 8193 (`KFAULT_PC`) and 8196 (`BOX0_HI`) returns 0 on both engines.
   - CPU oracle: `test_f1_mmio_config_block_user_ld_reads_zero` passes (asserts `registers[3] == 0` and `registers[4] == 0`).
   - WGSL shader: On-device measurement on RTX 5090 (`probe_wgsl_mmio_read_af3e.py`) produces `ram_result_word: 0` for both D1 and D2 (de-fangs BK-55 aim step).

2. **F2 (Cooperative read sharing unchanged):**
   - xv6-nano fixture USER LD of word 1622 (`curproc`) succeeds unchanged.
   - `test_f2_cooperative_user_ld_global_succeeds` passes.
   - Scenario 6 (`test_ek1_bounded_user_store`) passes (asserts `st == [3, 3, 5]`: `[DONE, DONE, FAULTED]`).
   - Scenario 11 (`test_go5_e2e_on_gpu[11]`) passes in 1.81s.

3. **F3 (GO-2 tile isolation intact):**
   - `spawn(..., tile=...)` USER LD out-of-tile traps with E-K1.
   - `test_l1_out_of_tile_ld_traps` passes (`rc == EXIT_FAULT`, `cpu.faulted is True`, `fault_addr == 164 * 4`).
   - `test_l2_in_tile_ld_unchanged` passes (`rc == EXIT_OK`, in-tile read succeeds).
   - `test_l3_boundary_word_traps_on_both_ld_and_st` passes.
   - `test_l4_super_mode_ld_unaffected` passes.
