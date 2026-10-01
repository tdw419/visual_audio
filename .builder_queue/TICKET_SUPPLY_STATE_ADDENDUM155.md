# TICKET SUPPLY STATE — ADDENDUM 155 (2026-09-17 01:2x, builder cron af3e62239ce2)

Re-measured at HEAD `2da0ce8`.

1. **Census clean**: roadmap scan (`.builder_queue/scan_open_rows.py` logic, ⏳ without
   `→ ✅` transition) → **OPEN=0**. Backlog exhausted (BK-1..BK-14 + OBS-1 all landed).
   Standing-instruction DEFECT-17/18 picks remain STALE — both gates re-run green this
   tick: `tests/test_defect17_x31_refusal.py` + `tests/test_defect18_tick_regfile.py`
   **13 passed** (`11fe1ac` / `7a4208a` landed).

2. **GO-5 residual closed to seat-only**: post-BUG-A s11 re-run GREEN x2 per
   `a4c077c` — re-confirmed this tick: `tests/test_rv64i_to_glyph_xv6_nano.py -q -p
   no:randomly` → **13 passed in 41.35 s** at `2da0ce8` (s11 included). Remaining open
   item is **BUG B (fault-window box-reg ownership)** — policy class, reserved to
   Jericho per `RULING_go5_residual_scheduler_yield_divergence.md` § Needs-Jericho.
   Nothing mechanical left for the loop.

3. **GO-6 L2 actively sibling-owned, advanced past pre-flight**: since this cron's own
   pre-flight receipt `2da0ce8` (00:54), the sibling lane created
   `kernel-builds/l2_rv32ima.fragment` (01:01, rv32ima-nommu virt config fragment with
   VIRTIO_BLK/VIRTIO_MMIO), an empty `kernel-builds/linux-6.9-nommu/` source dir
   (00:55), and **already produced `l2_test/Image_6.9_nommu_virtblk`** — i.e. the (a)
   build route was executed by the sibling while this cron's identical 6.1.14 tarball
   download (`/tmp/l2build`, sha256 prefix `a2707601`) was in flight. The sibling is
   now mid boot-smoke debugging: `diag_*.py` chain 01:06→01:17, last artifact
   `diag_tickrate2.py` 01:17, `smoke_uart_120M.txt` 3.5KB captured at 01:05. No build
   processes running at 01:28; the interactive diagnostic chain is A-state work in
   `kernel-builds/`, outside this repo, and per the no-collision rule neither the
   kernel-builds lane nor the sibling's WGSL/CPU files are touched by this cron.
   The 6.1.14 tarball is kept in /tmp as a fallback source (volatile; do not key
   anything to it).

4. **Capacity pressure**: `/home` is **100% full, 2.1G free** — any kernel-build or
   image artifact landing under /home risks filling the disk mid-write. Flagged for
   Jericho: the L2 route should target `/` (8.1G free) or get a cleanup pass first.

**Conclusion: HOLD again this tick.** Census clean; GO-6 L2 + SE021 remain
sibling-owned (kernel-build artifacts and gate files fresh minutes before this run);
GO-5 is seat-blocked (BUG B). No eligible supply. The only tree changes this tick are
this addendum; the standing gates (DEFECT-17/18 + xv6_nano 13/13) re-verified green.
