# TICKET SUPPLY STATE — ADDENDUM 110 (builder cron af3e62239ce2, 2026-09-16 ~15:1x CDT)

**Head at scan:** `d296d0c` (addendum 109). Branch `defect-d-ram-scoped-handlers`. Monitor: `DIRTY_ACTIVE`
(the 188 dirty files are the PXC1/virtio guest-runtime lane's — `tools/pxc1/src/lib.rs`,
`systems/virtio_pixel_rs/**`, `ubuntu_desktop_pxc1_v3_selfhost/frame_*.png` — NOT engine/codec files;
engine tree at HEAD is clean except one file, see §4).

## 1. Roadmap census: GLYPH_SELF_HOSTING_ROADMAP.md OPEN=0

Re-scanned this tick with a transition-marker scan (`.builder_queue/census_open_rows_this_tick.py`):
75 rows, **0 open** — every `⏳ queued` marker in a status cell is promotion provenance followed by a
`→ ✅ done` transition; no row's terminal marker is queued/defect/draft. This matches addenda 100–109.
No backlog promotion: GLYPH_BACKLOG.md remains exhausted (BK-1..BK-14 + OBS-1 all landed).

## 2. Backlog (d) — COMPLETE and re-verified at d296d0c

All 5 handlers landed (fd24c76 → e898bc2). Standing gate this tick (own run):
`tests/test_defect_d_ram_scoped_handlers.py` → **25 passed** in 1.1s.
`IMAGE_SPACE_WRITE_SYSCALLS = {0x11: 1}` is terminal (tools/glyph_isa_v2.py:373).

## 3. Arc leg A certification (own run, this tick)

`SEED=202609161510 tools/arc_lega.sh` at head `d296d0c` → **rc=0, 373 passed / 1 skipped /
9 deselected / 2 xfailed, 75.04 s, crashes=0, oom_kill_delta=0**.
Log `output/arc_lega_seed202609161510_d296d0c.txt` (+ .json sidecar). This is the standing
regression gate for the tick; no repo-wide sweep ran (exclusivity clause).

## 4. THE OPEN SUPPLY — GLYPH_ISA_ROADMAP.md Pillar 2.2a, WGSL READ dest-view divergence

The ISA roadmap (not the self-hosting roadmap the census covers) has one measured, ruled, and
NOT-started divergence that is the cheapest next eligible unit. Measured this tick by direct read:

- **Python engine (post-(d))**: SYSCALL_READ (0x02) writes the drained ring bytes to **RAM**
  (`self.memory[addr+i]`, tools/glyph_isa_v2.py:1440 — "LD-readable … NOT image/pixel space").
- **WGSL twin (unmigrated)**: syscall 2u still writes dest to **IMAGE space** via `mem_write(addr+i, b)`
  (tools/wgsl_glyph_isa_v2.py:575-600, comment says "Dest is image space via mem_write").
- Consequence: the two engines diverge on WHERE the read bytes land; a byte the Python engine can
  LD back, the WGSL engine cannot (WGSL LD/ST target image space, so on WGSL the bytes are
  LD-reachable and on Python they are not — the observable program behavior differs per engine for
  any program that READs and then LDs the buffer). The existing parity gate
  `tests/test_se022a_read_parity.py` checks **r9 only** (both engines return n=3) and never checks
  the dest bytes, so the divergence is GREEN-invisible today — exactly the papered-over comparison
  Pillar 3's ruling predicted (GLYPH_ISA_ROADMAP.md:185-193).
- The going-forward rule from backlog (d)'s correction (test_defect_d_ram_scoped_handlers.py
  docstring): **every handler lands on BOTH engines in the same commit, with its own WGSL/cross-engine
  parity leg**. 0x02 predates that rule and is the last handler violating it (0x01 landed WGSL-side in
  1c7c50f; 0x03/0x04/0x08/0x09 have documented-stub legs because GPU lanes have no FS/audio).

**Proposed next rung (mechanical, no design judgment): migrate WGSL READ's dest to `ram_write`
(the binding-5 RAM buffer landed with 0x01, tools/wgsl_glyph_isa_v2.py:103/208), same commit adds a
cross-engine parity leg asserting the dest bytes land in `receipt["ram"]` on WGSL == `self.memory`
on Python.** RED first: a leg that reads WGSL's `receipt["ram"][addr]` today gets 0 while Python's
`cpu.memory[addr]` has the bytes. Triple-sync (test_wgsl_triple_sync.py) + pre-commit WGSL hook
(.git/hooks/pre-commit:60-77, mirror at glyph_dispatch/tools/run_precommit_check.sh) cover the
sync mechanics.

**Why this tick did not implement it:** sibling process 3845928 (claude, started 13:15) is LIVE
(ps confirmed this tick) and the file-contact protocol (addenda 103–109) holds the loop off engine
files while a sibling session is active in the same tree. `tools/wgsl_glyph_isa_v2.py` and
`glyph_dispatch/src/glyph/wgsl_glyph_isa_v2.py` last commit 1c7c50f 12:30 (mine); no sibling
contact on the WGSL twin since (mtime + git log checked). Per the same protocol that governed
handlers 3–5, the rung is CLAIMED-not-started: pickup condition = no sibling contact on
`tools/wgsl_glyph_isa_v2.py` for 30 min at next tick's scan AND no 0x02-migration commit on any
branch. Handler 3/5 waited one hold tick under the identical condition and landed clean.

## 5. Also filed, not eligible this tick

- **Pillar 2.3 parity-CI leg** (GLYPH_ISA_ROADMAP.md:139) — depends on 2.2a's fix per the
  roadmap's own sequencing ("its READ leg depends on 2.2a's fix").
- **Pillar 1.3 comparison flags** — [J-DECISION: SE025 vs fold into SE024] is an unruled design
  question → BLOCKED-ON-DESIGN, exempt from self-promotion.
- **Pillar 5 (LLVM IR→Glyph)** — filed 1ec2a2a as NOT STARTED; its own text says the first real
  design pass (IR subset, SSA strategy, replace-vs-alongside) is undecided → design judgment, exempt.
- **DEFECT-22E** — measured-negative probe series, reopen-on-evidence only (unchanged).

## 6. Not verified this tick

- WGSL/GPU legs beyond the standing 25-leg suite + triple-sync (determinism rule: non-blocking).
- No claim about sibling 3845928's intent — only its liveness (ps) and file-contact history.
- The dirty PXC1/virtio tree is another lane's work-in-progress; I did not build or test it.
