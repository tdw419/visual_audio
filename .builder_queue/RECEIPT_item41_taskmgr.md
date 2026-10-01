# RECEIPT — item-41: Dynamic process lifecycle & spatial task manager

Builder: af3e62239ce2 (Glyph OS Event Chain cron). Claim: HEAD eaddb5a0
(monitor fingerprint matched), tracked-dirty = 0, mailbox rule clean
(`find .builder_queue -name 'RULING_*.md' -newermt @1790476433` EMPTY).
Brief: .builder_queue/BRIEF_item41_taskmgr.md — check_brief PASS,
--self-test exit 0 (both run before implementation).

## What landed

- NEW tools/glyph_taskmgr.py — GlyphTaskManager over the item-26
  GlyphProcessTable + item-38 GlyphCompositor (pure consumer; zero new
  syscalls; N1 pins glyph_isa_v2.py md5 5a672d7d5a94a7b20f927f554b8a90c0
  = HEAD's blob):
  - pause(pid)/resume(pid): manager-side overlay set (the landed
    table's state machine drives _run_task's re-entry guard and is
    NEVER overloaded); loud refusals on unknown pid / exited task /
    not-paused resume.
  - kill(pid): SIGKILL analog at a run boundary — a not-yet-run task
    is reaped 'exited'/EXIT_FAULT with NO guest execution (PRT stream
    empty — total by construction, honestly NOT a mid-run kill);
    refusal loud on an already-exited task, record unchanged.
  - run_ready(): advances every non-paused, non-exited tracked task
    one cooperative run; marks windows reaped on the compositor's LIVE
    _windows record (comp.window() returns a COPY — mutating the copy
    silently no-ops; found by T7, fixed, see defects below).
  - open_manager()/refresh(): a real fenced manager tile at the locked
    rect (2,0) 7x4; drives ONLY its own pid through table.wait() —
    comp.run_all() is compositor-global and would execute application
    tasks that are merely being DISPLAYED (a task list must not run
    apps); refresh respawns at the same rect with re-seeded state
    words (item-40 _repaint_tray shape).
  - The manager guest paints one state cell per task from kernel-seeded
    words at its own tile origin (TILE_ROW/COL idiom): green ready,
    amber paused, red exited-fault, dim gray exited-ok; a zero seed
    word paints nothing.
  - close_window(wid): reaped-only retirement via set_visible(False)
    (append-only records); non-reaped close refused loud.

## Gate (tests/test_item41_taskmgr.py, 10 legs: T1..T8 + N1 + N2)

GREEN tail (own run, output/item41_green_final.txt):

    10 passed in 0.07s
    GREEN_RC=0

RED legs (driver .builder_queue/red_driver_item41.sh; module restored
byte-exact between runs — md5 3667df7c4b7950083ab94bd964321a49
asserted before/after each mutation):

RED 1 — run_ready() ignores the paused state (output/item41_red1.txt):

    FAILED tests/test_item41_taskmgr.py::test_t3_pause_resume - assert {1, 2} == {2}
    FAILED tests/test_item41_taskmgr.py::test_t8_fence_governs_and_lane_survives
    2 failed, 8 passed in 0.08s
    RED1_GATE_EXIT=1

RED 2 — kill() marks EXIT_OK instead of EXIT_FAULT
(output/item41_red2.txt):

    FAILED tests/test_item41_taskmgr.py::test_t2_kill_before_run_never_executes
    FAILED tests/test_item41_taskmgr.py::test_t5_manager_tile_paints_states - Ass...
    2 failed, 8 passed in 0.10s
    RED2_GATE_EXIT=1

Both REDs discriminate: each mutation flips the legs it targets (T3/T8
and T2/T5 respectively) while the untargeted legs stay green.

Adjacent regression on this tree: item-38 + item-39 + item-40 gates —

    28 passed in 0.13s

## Gate-caught defects fixed in-scope (all in the NEW module)

1. run_ready() set the TABLE task's state to "running" before wait()
   — tripped the landed _run_task re-entry refusal
   (glyph_process.py:198-199). Fixed: the table's state machine is
   never written by the manager; pause lives in a manager-side set.
2. run_ready()/open_manager() used comp.run_all(), which is
   compositor-global: it would execute app tasks that are merely being
   displayed. Fixed: scoped runs — the manager waits only its own pid
   (open/refresh) or its tracked pids (run_ready).
3. The reaped flag was written through comp.window(), which returns a
   COPY of the record (glyph_compositor.py:172-173) — the mutation
   silently no-oped (T7 caught it). Fixed: write to
   comp._windows[wid] directly.
4. First-draft state-cell address mapping disagreed between the guest
   painter and the seed/test (T5 caught it). Test aligned to the
   landed guest-paint idiom (origin + i cells); no guard weakened.

## Honesty / what this PASS does NOT prove

- No GPU/WGSL execution — host CPU-oracle engine (N1 pins the engine
  blob to HEAD).
- kill() is a RUN-BOUNDARY reap, not mid-run termination; "signals"
  here have no preemption/interrupt semantics (cooperative
  commit-between-runs, item-26/34/40 doctrine).
- The manager-side pause overlay is scheduler-visible state, not a
  delivered POSIX signal; there is no SIGSTOP-equivalent for a task
  already running (the landed cooperative refusal IS the semantics).
- close_window() is set_visible(False) retirement (append-only
  records) — the window record still exists, exactly as item-40's
  expire model.
- No rates/latencies asserted anywhere (rule-1 floors do not attach).

## Queue state

- QUEUE_STATE.json: item-41 -> landed (this commit).
- CLAIM QUEUE empty beyond item-41. Next tick: Phase 1c research tick
  per the ledger protocol, unless a new CLAIM QUEUE item / RULING
  appears first.
