# PRODUCT_ROADMAP.md — Glyph GPU OS as a chosen product

**Status:** RATIFIED 2026-09-21 (Jericho). R1.3 gate amended: failure rate is
load-bearing (isolation is the actual thesis), not one of three interchangeable
metrics — see R1.3 below.
**P1 RESULT:** R1.3 measured PASS 2026-09-21 (tie on failure rate + win on
wall-clock under the amended gate) — P1 thesis CONFIRMED; see
`.builder_queue/RECEIPT_R13_preference.md`. P2 (the box ABI) is next.
Caveat carried in the receipt: the PASS is on the CPU-oracle substrate —
the WGSL shader twin remains functionally divergent (fleet probe halts at
153 with all fleet words 0) and that convergence gap is the lane's largest
open defect.
**Predecessor:** GPU_CPU_EMULATOR_ROADMAP.md (closed: generated toolchain,
GPU-resident execution, multi-hart parity, PS009 fork closed on distribution at
`396bc8ed`). That roadmap's non-goals — MMU/privileged arch, drivers,
interrupts, floats, real-hardware bring-up, userland — are this roadmap's
backlog.

---

## 0. The honest scale statement

"Replace an existing OS" is a destination, not a task. Daily-driver
replacement is a decade-scale claim. The gate that matters and is achievable:

> **Jericho chooses to boot into it every morning and does his real work in
> it.** His daily use is the only acceptance test that counts — per the
> standing rules, the operator is the first user, and no agent may declare
> this roadmap complete on his behalf.

The product cannot be "Linux but slower on GPU" — a generated RV32 interpreter
on wgpu will never out-native a native x86 kernel. The product is the thing
only this stack can be: **a GPU-native OS where the shader IS the machine** —
box-ABI per-tile isolation, mailbox oracle, Hilbert-coherent spatial memory —
doing what host OSes cannot: massively parallel agent workloads with spatial
isolation at scale. First proof: one workload you'd rather run there than on
Ubuntu.

## 1. Phases (each phase = rungs with falsifiable gates, one rung + demo + tests per session)

### P1 — The anchor workload (why switch?)
- **R1.1** Pick the workload: autonomous agent fleet — N isolated agent tiles
  communicating by mailbox, supervised by the seat, running real tasks
  (codegen sweeps, triage, monitor loops) for hours unattended.
  Gate: one full agent task completes in-guest, output verified host-side.
- **R1.2** Fleet demo: ≥4 concurrent isolated agents, no cross-tile fault
  propagation (fault-injection RED leg required — see policy rule 4).
- **R1.3** The preference measurement: same task, GPU-OS lane vs Ubuntu lane,
  wall-clock + cost + failure rate. Gate: GPU lane must win or tie on
  **failure rate** (the isolation thesis is the actual claim; wall-clock and
  cost correlate with each other and must not carry the gate alone) PLUS at
  least one of {wall-clock, cost}. If it never wins, this roadmap's thesis
  is false and P2+ is a rewrite.

### P2 — Make the box a machine people program (the ABI)
- **R2.1** Freeze the box ABI: syscalls, register layout, memory map, mailbox
  protocol — versioned, with a conformance suite (GREEN + RED legs).
- **R2.2** Toolchain UX: one command compiles a program to a glyph/tile
  artifact and runs it. Target: someone who has never read this repo.
- **R2.3** Hosted cross-compilation story: C/Rust via RV32 target, LLVM
  backend or transpiler chain, round-trip receipts.

### P2.5 — The desktop floor (AMENDMENT_DTF1_desktop_floor.md, RATIFIED 2026-09-22)
Activated by the R5.3 day-1 use finding ("no user surface exists yet",
R53_USE_LOG.md, 3d0b09d5). Bar: GPU OS comparable to first CPU desktop
systems (Altair/Apple II/early-DOS era) BEFORE the operator resumes daily
real-use testing. Exit: one end-to-end transcript receipt
(RECEIPT_DTF_floor.md) exercising all of it in sequence, plus each row's
own gates. R5.3's 30-day clock is NOT reset (amendment clock clause).
- **DTF-1** glyph-sh v1 dispatch (e/s/w/r on first byte, loud unknown-cmd
  error). ✅ DONE 2026-09-22 — receipt `.builder_queue/RECEIPT_DTF1_shell_dispatch.md`:
  implementation is TASK_SE020 (commit 2227ebc5, 2026-09-15); measured at
  HEAD 4e3c30a2 this session — gate 17 passed rc 0, RED-first (test file
  absent → pytest collection error), one-instance transcript of all five
  legs PASS incl. mutation (always-echo build echoes verbatim, no marker).
- **DTF-2** in-image text console: glyph-rendered session text ON the GPU
  screen (glass-TTY honest boundary; scrolling = bounded ring of text
  rows). Engine change ADDITIVE only. Gate (minimum legs): RED-first blank
  sentinel pixel-region read before first write; known string written →
  glyph-side pixel-region read decodes it back; WGSL twin byte-identical
  console band; full engine + twin regression green.
- **DTF-3** FS grow (BK-7): SYS append + resize, FSTAB compaction. Gate:
  `tests/test_bk7_fs_grow.py` RED-first — write, append 2×, read back
  byte-exact; delete → hole; new create reuses it. WGSL twin: host-side
  FS handlers → twin-boundary note per SYSCALL_ABI_SPEC convention.
  ✅ DONE 2026-09-22 — implementation is BK-7 (commit 153b5edb, 2026-09-11);
  measured at HEAD 2629d9a5 — gate 2/2 green + 67-test family green, WGSL
  twin boundary MEASURED (premise corrected: FS kernel is in-image guest
  code, executes on the shader path with word-exact RAM state, 273 steps
  both engines, zero non-MMIO diffs; probe
  `.builder_queue/probe_dtf3_twin_boundary.py` exit 0 MATCH + corrupted-
  expectation RED exit 1). Receipt `.builder_queue/RECEIPT_DTF3_fs_grow.md`.
- **DTF-4** coreutils vol. 1 (BK-11): cat/echo/wc/cmp/head via
  riscv64-gcc + glyph_cc, byte-exact vs native on 3 fixtures each,
  RED-first. `wc` must go green or its DEFECT-18-class defect fixed — no
  waiver. Depends on DTF-3.
  ✅ DONE 2026-09-22 — gate found REGRESSED at HEAD 2090c163 (cat/echo/wc/
  head 0/3 fixtures, OOB-store faults; only cmp green) — RCA: R2.3 commit
  6605f41a (09-21) excluded ALL ABS ELF symbols from parse_elf's table,
  deleting `__global_pointer$`, which the GH-23 loader seeds into x3
  (DEFECT-9 contract); gp=0 → gp-relative small-data accesses fault
  0xFFFFF80C-class. Bisect-pinned (564a05af..HEAD → 6605f41a). Fix:
  FILE symbols excluded by type (ABS+FILE), not ABS-ness — gp restored,
  R2.3's original shadow bug still fixed. Gate GREEN 6/6 (incl. wc, no
  waiver needed — DEFECT-18(a) landed 11fe1acd); R2.3/gh23/gh21/gh26/bk14
  + 20 transpiler files green; arc SEED=42 394 passed rc=0. Receipt
  `.builder_queue/RECEIPT_DTF4_coreutils.md`.

**FLOOR EXIT (2026-09-22):** end-to-end transcript receipt
`.builder_queue/RECEIPT_DTF_floor.md` (generator
`.builder_queue/transcript_dtf_floor.py`, exit 0; corrupted-expectation
RED leg exit 1) — all four rows exercised in sequence. P2.5 floor-exit
criteria MET in the amendment's checkable sense. Remaining: the agent
pre-verification receipt (RECEIPT_DTF_agent_use.md — correctness, never
usability per the amendment's binding wording); usability itself is the
operator's day-2 R5.3 entry.

### P3 — Boot and persistence (the daily-use floor)
- **R3.1** Cold boot to agent-fleet-ready <60s on this hardware, measured,
  receipts with floors attached (policy rule 1).
- **R3.2** Persistence: tile state + outputs survive power cycle (PXC1/VAC
  containers or the virtio-pixel backend's writeback), crash-safe (kill -9
  RED leg).
- **R3.3** Host integration: the OS is reachable from the host seat the way
  the current guest is (SSH/bridge), file exchange verified both directions.

### P4 — Drivers and device reality
- **R4.1** Keyboard/mouse input into the mailbox path (BM905 lineage).
- **R4.2** Display output: pixel-perfect frame presentation, VCC-preserving.
- **R4.3** Storage: block device with the writeback contract, ENOSPC-safe.

### P5 — The choice (packaging the product)
- **R5.1** An installer/launcher artifact: one file, boots on Jericho's
  machine (and a second machine, if one exists).
- **R5.2** Documentation a stranger can follow: what it is, what it's for,
  how to run the anchor workload.
- **R5.3** ~~The 30-day gate: Jericho boots it for real work ≥15 days in 30.
  Measured by his own report.~~ **WAIVED BY OPERATOR 2026-09-23** ("i dont
  want to have to answer any questions or do the 30 day thing. please just
  make the software." — see RULING_R53_disposition in PRODUCT_LANE_STATE.md).
  Launch criterion is now: desktop floor complete (DTF-1..4, per
  AMENDMENT_DTF1_desktop_floor.md) + agent pre-verification receipt
  (RECEIPT_DTF_agent_use.md). Day-1 entry (3d0b09d5) stands in the use log
  as a true record; the gate was waived, not failed.

## 2. Non-goals (standing, unless a phase result forces revision)

- Out-native-ing Linux on throughput. We win on isolation-parallelism, not
  raw speed.
- General consumer desktop (GUI file managers, web browsers). The product is
  an agent/workload OS with a seat, not a ChromeOS competitor.
- Any claim of "OS replacement" in public copy until R5.3 passes.

## 3. Standing policy hook

All work under this roadmap executes under
`.builder_queue/POLICY_standing_decision_delegation.md` (if ratified) plus
`POLICY_decision_delegation_20260918.md` (in force): measure → safe default →
land with receipts; floors attached to every rate; RED legs shown at landing;
48h escalation on measurement flips. Named hold-gates (BM001, GO-6) remain
auto-DECLINE.

/s/ drafted by the seat lane, 2026-09-21 · ratified by Jericho, 2026-09-21 (R1.3 amended)
