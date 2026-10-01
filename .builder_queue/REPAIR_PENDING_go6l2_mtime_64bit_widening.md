# REPAIR PENDING — GO-6 L2: 64-bit mtime widening in the RV32 spatial engine

**Filed:** 2026-09-18, builder cron af3e62239ce2
**Blocks:** GO-6 Layer 2 (gate: vd0 appears + dd round-trip) — kernel is proven
sound on real hardware (`/home/jericho/projects/zion/kernel-builds/l2_test/QEMU_REFERENCE_VERDICT.md`),
boot stalls ONLY in `SpatialRV32ICore` (`FINDINGS_go6_l2_stall.md`: mtimecmp
freezes at 12155141, MTIP latched, hot timer-IRQ livelock at ~8M steps/tick).

**Measured:** QEMU runs the identical `Image_6.9_nommu_virtblk` past the stall
milestone in <1s (`clocksource: Switched to clocksource clint_clocksource`,
mask 0xffffffffffffffff). Divergence is emulator-side; leading candidate is the
engine's 32-bit mtime (`SPATIAL_RV32I.wgsl:998`, 32-bit comment `:20-23`)
against a kernel reading mtime as 64-bit. NOT proven that mtime width is THE
cause vs other CLINT modeling gaps.

**This is a skeleton-sign-off / engine-fence change.** `SPATIAL_RV32I.wgsl`
(+ the Python twin `spatial_rv32i_cpu.py` for lockstep parity) is a shared
engine file — baked images, WGSL parity gates, and the GO-6 L1 receipt all
touch it. Standing rule: zero engine lines without a ruling. **Holding.**

## Options (cheapest-first)

1. **Scope-limited 64-bit mtime/mtimecmp widening** — change ONLY the mtime
   counter/comparator arithmetic to 64-bit (uvec2 hi/lo or f64), keep the
   register surface +1/+2 words additive, re-run `tests/test_spatial_rv32i_cpu.py`
   (19 passed at L1 merge) + boot-smoke gate + a new parity leg proving
   `timekeeping_advance` progresses past 13M steps. Cost: moderate; risk: baked
   images with a frozen register layout (L1 receipt) need re-bake check.
2. **High-word-only shim** — keep 32-bit mtime but return a latched hi-word on
   CLINT_BASE+4 reads so the kernel's 64-bit read never goes backward. Cheaper,
   less honest; the counter still wraps at 4G steps (~2h at 35k steps/s).
3. **Interpose QEMU** — accept QEMU as the L2 dev loop (boot, vd0, dd round-trip
   all provable there) and file the emulator stall as its own DEFECT. Fastest
   path to the L2 gate clause, but it changes what the layer claims (no longer
   "on the GPU-native substrate") — needs an explicit scope ruling.
4. **Declare the stall out of scope for L2** — gate the layer on QEMU-hosted
   virtio-blk proof + emulator transport-only proof (L1). Weakest claim; listed
   for completeness.

Options 3/4 change the meaning of the layer; options 1/2 change the engine.

**RESOLVED-BY-DECLINE 2026-09-18** (host session, policy D-3 of `POLICY_decision_delegation_20260918.md`): the blocker seat is freed — no more holds counting on this note. Disposition and reasoning: `.builder_queue/DISPOSITION_go6l2_mtime64_declined_20260918.md`. Short form: option 1 remains the evidence-backed fix and the DRAFT ruling + brief stay staged and inert; what's missing is solely Jericho's verbatim ratification word ("option 1 ratified"), which a standing delegation cannot backfill (4x-flagged rule, 2026-09-14). Zero engine lines. GO-6 L2 gate remains honestly OPEN as a capability gap.
Decision needed from Jericho before any engine line is written.
