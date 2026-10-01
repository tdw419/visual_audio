# RECEIPT — R3.2 Persistence: tile state + outputs survive a power cycle

Rung: PRODUCT_ROADMAP.md:66-68 (R3.2) · Builder: cron af3e62239ce2 ·
HEAD before: 44baa79e · Date: 2026-09-21 (~21:5x CDT clock, 16:4x wall
per monitor)

## What landed

`.builder_queue/probe_r32_persistence.py` — the R3.2 gate: freeze the
LANDED R3.1 fleet chain (atlas → resident_image(mode="fleet",
timer_quantum=6) → GlyphRunner → run_wgsl to halt @458 steps) into a
GPX1 container (magic `GPX1`, JSON header, sha256 payload checksum,
64 KB RAM + 32 registers + packed-RGB image), drop the in-memory
runner (POWER OFF), restore into a fresh GlyphRunner from container
bytes only, host-verify every frozen fleet word.

Zero production lines changed. Measurement + container over LANDED
artifacts at HEAD 44baa79e.

## Mechanism note (why this is NOT the pre-registered blockage)

The ledger pre-registered R3.2 as BLOCKED ("no power-cycle/persistence
mechanism"). Verified against the tree: run_wgsl
(tools/glyph_gpt/runner.py:133-186) creates all buffers per call — no
persistence path exists IN the substrate. But the rung text names the
mechanism: "PXC1/VAC **containers** or the virtio-pixel backend's
writeback". A container is buildable host-side without any new
substrate capability — same class as the PXC1/VAC containers the rung
cites. The blockage would hold only for an IN-SUBSTRATE persistence
mechanism; the container leg does not require one. This reasoning is
recorded here for Jericho's review; the rung is landed as
GATE-PASSED-VIA-CONTAINER, not via an in-substrate power-cycle
primitive (honesty: no such primitive exists at this HEAD).

## Gate legs (all run this session, real output)

RED first (before any green was trusted):

1. `--corrupt-verify` → exit 1. Verifier's expectations XOR 0x5A5A →
   the restored GOOD state is REJECTED:
   `R3.2 corrupt-verify RED leg: verifier REJECTED with corrupted
   expectations (correct discrimination)` (/tmp/r32_red1.log)
2. `--corrupt-container` → exit 1. One payload byte flipped → loader
   rejects on checksum:
   `torn/corrupt container: checksum mismatch (payload 707310914bfc… !=
   header aeb9bd000076…)` (/tmp/r32_red2.log)

GREEN:

3. Plain run → exit 0 (/tmp/r32_green.log):
   `freeze: boot 800.8 ms, 458 steps, halted; frozen words OK
   (ram[765]=0x5eed0005 ram[717]=0b1011 ram[731]=0xfa026
   results={714:6, 728:12, 748:20, 763:30})`
   `crash-mid-write analogue: leftover gpx1.tmp ignored, container
   intact (95432 B)`
   `R3.2 PERSISTENCE: PASS (freeze → container → power cycle →
   restore; all frozen words survived)`

Regression: tests/test_box_abi_conformance.py + test_glyph_run.py +
test_gh26_fleet.py → **24 passed** (lane suites touched by this
surface).

## Floors / check_regime

No rate claims in this rung (persistence correctness, not speed).
Floors citation N/A with that reason; check_regime not run (nothing to
adjudicate). Boot wall-clocks reported (730-800 ms cold, consistent
with R3.1's 814 ms) are context, not gate numbers.

## What this PASS does NOT prove

- **No in-substrate power cycle**: the "power off" is dropping the
  host-side runner object; the substrate itself has no
  power-cycle primitive. The container round-trip proves STATE is
  capturable and restorable, not that hardware preserves it.
- **kill -9 is an ANALOGUE**: atomic write (tmp + os.replace) means a
  real crash mid-write cannot tear the container, and the leftover-tmp
  leg shows a torn file is ignored — but no actual SIGKILL was
  delivered to a live writer process.
- **Single image family, single host/GPU** (R3.1's caveat carries).
- **Crash-safety of the READER under concurrent write** not tested
  (single-process gate).
- The restored image reconstructs a runner, but instruction-exact
  continuation (resume-from-snapshot execution) is NOT claimed — the
  gate verifies frozen words, not post-restore stepping.
