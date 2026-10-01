# TICKET SUPPLY STATE — ADDENDUM 280 → 281

**Tick:** 2026-09-18 ~09:55 CDT · **Base:** ea3cc949 (BM-501 rung-5 landing) ·
**Branch:** glyph-transpiler-autoloop

## Supply scan

`tools/supply_census.py` → `TOTAL=79 OPEN=0` rc=0. Backlog BK-1..BK-14 + OBS-1
+ GL-6/7 landed; GL-6/7 publication-fenced to Jericho, GL-8+ human-gated.
BM-501 (rung 5) landed as HEAD ea3cc949 — this tick **independently re-ran**
`bash run_gate5.sh` from the committed tree: **exit 0, GATE PASS** (greenA/B/C
byte-identical `CRC=329CD470 IMG2 CRC=7880D4BA WRITE=OK STAGE2 CKSUM=43E6 EXEC`,
redA exact refusal `B3AEA74F EXP=7880D4BA`, non-vacuity shows the neutered check
passing a corrupted medium, RE-GREEN byte-identical). Log
`tools/bare_metal_poc/rung5/gate5_reverify_orch_094848.log`. Receipt claims
verified, no repo changes needed for rung 5.

GO-5 ✅ closed (roadmap `systems/GPU_OS_ROADMAP.md:393` block; gate green this
tick: `pytest tests/test_rv64i_to_glyph_xv6_nano.py -k go5 -q` → 1 passed,
exit 0; twin divergence was fixed via `RULING_go5_ptr_table_vs_bss` option 1 +
DEFECT-30 SRL/SRA fix). GO-6 Layer 1 ✅ done (f0ae1fa).

## GO-6 L2 — stall root-caused to the EMULATOR by QEMU reference run

Executed the probe FINDINGS_go6_l2_stall.md named. Same
`Image_6.9_nommu_virtblk` under `qemu-system-riscv32`:

- original DTB → early panic (QEMU has no CLINT at 0x11000000; its real CLINT
  is 0x02000000 — that address is the spatial emulator's model);
- DTB patched (clint@02000000, one change) → kernel passes the emulator's stall
  milestone in <1 s: `Ratio of byte access` at 0.45 s, then
  `clocksource: Switched to clocksource clint_clocksource` (mask 64-bit) — the
  `timekeeping_advance` path that livelocks SpatialRV32ICore (mtimecmp frozen,
  MTIP latched) completes cleanly. Later panic is `VFS: Cannot open root
  device "/dev/vda"` — the DTB has no virtio node yet, which is the L2 gate's
  own remaining work, not a regression.

**Verdict:** kernel config is sound (FINDINGS option B closed); divergence is
emulator-side, leading candidate the 32-bit mtime model
(`SPATIAL_RV32I.wgsl:998`). The fix is an engine change → fenced, holding.
Artifacts (probe + logs + `QEMU_REFERENCE_VERDICT.md`):
`/home/jericho/projects/zion/kernel-builds/l2_test/`.
Ticket: `.builder_queue/REPAIR_PENDING_go6l2_mtime_64bit_widening.md`
(4 options, cheapest-first; options 3/4 change the layer's meaning, 1/2 change
the engine — needs Jericho's ruling).

**HOLD continues** — L2 blocked-on-design, no other eligible supply.
Not verified this tick: no WGSL/engine lines touched (by rule), no arc re-run
(no repo code changed), SE021 maildrop untouched (BLOCKED-ON-JERICHO).
