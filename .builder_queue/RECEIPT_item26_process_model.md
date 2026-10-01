# RECEIPT — CLAIM QUEUE item 26: spatial process model (spawn primitive + multi-task coordination) (builder af3e62239ce2, 2026-09-26 ~06:1x CDT)

## What landed

Commit f8767491 on the main tree (work 208a87d4 in worktree
`/home/jericho/projects/zion/worktrees/item26-proc`, cherry-picked after
gates passed — the AGENTS.md blast-radius rule; no core engine file was
modified this time, but the worktree discipline was kept anyway since
the design started as engine-adjacent).

- `tools/glyph_process.py` (NEW, ~230 lines) — `GlyphProcessTable`, the
  spawn primitive + coordination layer:
  - `spawn(image, name=, vfs=, vfs_shared=)` -> pid. Each task runs in a
    FRESH `GlyphCPUv2` engine with its own RAM and register file — the
    SE021 isolation delta (tools/glyph_child_runner.py docstring), moved
    in-process: the table is a scheduler, not a shell verb.
  - Exit-status contract (mirrors glyph_child_runner.py rc semantics):
    explicit `SYSCALL 0x05 EXIT` r1 -> latched via an `_on_exit` hook on
    a `_TaskExitStatus` subclass (wraps `_handle_syscall`, calls super
    first — the base handler's rd-write and running=False are untouched);
    clean HALT / opcode-None silent halt -> 0; genuinely faulted engine
    -> 1.
  - `wait(pid)` / `wait_any()` / `wait_all()` — cooperative scheduling:
    no preemption, no signals, run-to-HALT per task (documented
    non-goals).
  - Coordination through the item-25 landed VFS: `vfs_shared=True`
    attaches ONE GlyphVfs to multiple task engines, so 0x03/0x04/0x13
    hits the same staged overlay — A writes, B reads, byte-exact.
- **ZERO new syscall numbers.** A Python-only process table adds no
  guest-visible ABI, so the WGSL twin's GeOS bridge (16u..255u) never
  sees a new number to mis-bridge — the TICKET_ITEM8 false-success class
  is structurally avoided, not argued around.
- `tests/test_item26_process.py` (NEW, 8 legs, force-added past
  .gitignore test_*.py).

## RED leg (shown FIRST)

Implementation stashed (`git stash push -u tools/glyph_process.py`) ->
collection error: `ModuleNotFoundError: No module named 'tools.glyph_process'`
at tests/test_item26_process.py import — the gate cannot even collect.
Restored -> full GREEN.

## GREEN legs

Worktree at 208a87d4: **8 passed in 33.11s**, exit 0. Main tree at
f8767491 (post-cherry-pick re-gate): **8 passed in 33.52s**, exit 0.

1. `test_p1_spawn_isolation_fresh_engines` — two tasks, distinct pids,
   distinct engines (`a is not b`); A's RAM word and r5 hold A's value,
   B's hold B's — no shared state.
2. `test_p2_exit_status_contract` — `EXIT r1=7` -> wait() == 7 (engine
   stdout shows `[SYSCALL] EXIT: status=7`); clean HALT program ->
   EXIT_OK(0); corrupted-opcode-pixel program (opcode-None silent halt,
   glyph_isa_v2.py:766-769 contract) -> EXIT_OK(0), state exited.
3. `test_p2b_faulted_engine_rc1` — engine driven to a REAL fault
   (misaligned PC -> SpatialMisalignmentFault) -> status EXIT_FAULT(1).
4. `test_p3_wait_all_three_tasks` — 3 concurrent spawns, wait_all
   returns all pids, all EXIT_OK, each PRT stream byte-exact
   (ALPHA/BETA/GAMMA).
5. `test_p4_shared_vfs_handoff_between_tasks` — THE coordination leg:
   task A 0x03-writes `handoff.txt` through the shared VFS; task B
   0x04-reads the same name and receives A's 21 bytes byte-exact in its
   own RAM; the file does NOT exist on the host FS (VFS-2 contract
   intact); ordering enforced by the table (A waited before B runs).
6. `test_p5_wait_any_and_state` — wait_any returns ready tasks in pid
   order, then the first exited pair without re-running; state()
   transitions ready -> exited; unknown pid raises GlyphProcessError.
7. `test_r1_bare_engine_exit_unchanged` — MIGRATION: a bare GlyphCPUv2
   (no table) runs the 0x05 program exactly as landed (rd == 9,
   running False). The base engine is byte-unchanged (the hook lives in
   the table's subclass).
8. `test_r2_item25_vfs_gate_still_green` — MIGRATION: the full item-25
   gate (tests/test_item25_vfs.py, 8 legs) re-run GREEN in this tree via
   subprocess.

Migration matrix (in addition to R1/R2): test_glyph_file_io.py +
test_l1_shell_personality.py + test_bk11_coreutils.py -> **23 passed**
unmodified on this tree.

## Probe/test defects fixed before evidence was trusted (disclosed)

1. First draft of P1 used `ST r5 <imm>` — ST's contract is
   `ST <addr_reg> <value_reg>` (glyph_isa_v2.py:439-446); the harness
   program was wrong, not the engine. Fixed to LDI r6/ST r6 r5.
2. First wait_any preferred already-exited tasks over ready ones — the
   P5 leg caught the (1==2) ordering; contract corrected to
   ready-first-in-pid-order.
3. P2's first draft tried to force a fault with a numeric JMP target —
   the assembler takes `col,row` (SE023 bounds check); dead exploration
   removed, the real fault leg moved to P2b (misaligned PC).
4. R2's subprocess used the worktree .venv which is a bare python3.11
   with no pytest (main tree's .venv has it) — the leg now probes for a
   pytest-capable interpreter first (environment guard, the
   REPAIR_PENDING_se021_spawn_interpreter_resolution precedent class).

## Honesty / what this PASS does NOT prove

- No GPU-image execution: tasks run on the host CPU engine
  (GlyphCPUv2), Phase-2 doctrine. Nothing spatial changed; no
  VCC/Hilbert surface touched; the WGSL twin is untouched and its
  contract untouched (no new syscall numbers) — but twin parity was NOT
  re-pinned because there is no engine/glyph-side change to pin.
- Cooperative only: no preemption, no timer-yield scheduling BETWEEN
  tasks (GH-16's in-engine tick is per-engine and untouched), no
  signals, no background jobs, no shared RAM between task engines.
- The L1 shell has no spawn verb yet — wiring spawn/wait into
  GlyphL1Shell (job control surface) is a later ladder step; this item
  is the primitive + table, per the supply title.
- wait() runs the task in the CALLING thread (no true concurrency);
  "multi-task" = multiple tracked task engines with isolated state and
  a shared coordination channel.
- Rule 6: all asserts structural (statuses, bytes, states, pid order) —
  no rates/latencies, rule-1 floors do not attach; check_regime not
  implicated.

## Files touched (git scope check done)

- NEW tools/glyph_process.py, tests/test_item26_process.py. Nothing
  else: `git status --short` clean on both trees post-commit; engine,
  baker, transpiler, WGSL shaders, protected assets untouched.
