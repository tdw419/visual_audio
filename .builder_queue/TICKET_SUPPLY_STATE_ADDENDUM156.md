# TICKET SUPPLY STATE — ADDENDUM 156 (2026-09-17 02:0x, builder cron af3e62239ce2)

Re-measured at HEAD `35a48c0`.

**Verdict: HOLD tick for roadmap supply (census OPEN=0 unchanged), but this tick
produced measured GO-6 L2 stall findings instead of a bare hold — evidence the
sibling lane's diag chain generated at 01:06-01:17 but never persisted.**

1. **Census clean**: `python3 .builder_queue/scan_open_rows.py` → exit 0, OPEN=0
   (unchanged from addendum 155). Backlog exhausted. DEFECT-17/18 remain landed;
   not re-run this tick (13/13 at `11fe1ac`/`7a4208a` stands, re-confirmed 01:33).

2. **GO-6 L2 — measured findings landed** (this lane, host-side spatial emulator,
   sibling lane silent since 01:17, no build processes running):
   - The stall after `Ratio of byte access...` is **not a wedge**: 24 PC samples
     over 120M steps spread across the timer/sched path, every sample
     mcause=0x80000007 (MTIP), mode=M. Stack walk (deterministic x2,
     byte-identical) is pure timer-IRQ:
     `clint_timer_interrupt -> tick_periodic -> update_wall_time ->
     timekeeping_advance -> timekeeping_update -> shadow_timekeeper`.
   - **NEW measured fact: `mtimecmp` freezes at 12155141 while mtime keeps
     counting from step ~13M onward → MTIP latched permanently → the CPU
     livelocks inside the timer interrupt.** (`diag_mtimecmp_result.txt`, new probe.)
   - Tick cadence measured: ~8M steps/tick at ~35k steps/s host ≈ 3.8 min/tick
     wall; UART frozen at 3578 bytes because each tick consumes minutes.
   - Prime suspect (hypothesis, labeled): 6.9 clint driver reading the mtime HIGH
     word (WGSL mtime is 32-bit only, `tools/SPATIAL_RV32I.wgsl:20-23,998`) or
     `timekeeping_advance` seqcount retry against permanently-latched MTIP.
   - Full chain + not-claimed list + cheapest next probes:
     `/home/jericho/projects/zion/kernel-builds/l2_test/FINDINGS_go6_l2_stall.md`
     (outside the repo by design — kernel-builds lane; zion monorepo shows
     `kernel-builds/` untracked, left that way per no-collision rule).

3. **GO-5 residual / SE021 / BUG B**: unchanged — policy class, seat-blocked on
   Jericho (`RULING_go5_residual_scheduler_yield_divergence.md`). Not touched.

4. **Capacity**: /home full flagged in addendum 155 — unchanged this tick; the
   findings above are text-only artifacts (KB), no build outputs added.

5. **Gate hygiene**: `git status` in visual_audio shows only the pre-existing
   sibling dirty set (virtio_pixel_rs, pxc1, ubuntu frames, guest context) plus
   long-standing untracked `.builder_queue` files. **This cron modified nothing
   inside the visual_audio repo this tick** — the one deliverable lives in
   `kernel-builds/l2_test/`. No commit needed; nothing to commit.

**Conclusion: HOLD on roadmap supply; L2 debug evidence persisted for the next
lane. The mtimecmp-freeze measurement is the concrete lead the 01:06-01:17 diag
chain was circling; it needs either a 64-bit mtime engine change (design ruling —
touches shared WGSL, affects baked images) or a QEMU golden-reference diff, both
of which exceed this tick's mechanical scope.**
