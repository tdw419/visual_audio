# BRIEF — item-41: Dynamic process lifecycle & spatial task manager
# (process kill/pause signals, interactive task manager tile, clean window close)

## Spec pointer

QUEUE_STATE.json item-41 (id item-41, claim_order 41, blocks_on
[item-38, item-39] — both LANDED: item-38 e9303ed2 lineage, item-39
a675d186; HEAD eaddb5a0 pins both). Consumes ONLY landed layers:
item-26 GlyphProcessTable (tools/glyph_process.py — the pid table,
cooperative _run_task, states ready/running/exited, EXIT_OK/EXIT_FAULT
contract), item-38 GlyphCompositor (tools/glyph_compositor.py —
place/run_all/composite/hit_test/set_visible, records append-only,
reaped-window move()), item-40 GlyphNotifyDaemon idioms
(tools/glyph_notify.py — guest-paint from TILE_ROW/COL, kernel-class
seed/harvest, respawn-repaint at a locked rect), item-39
GlyphVT/VT100Screen (tools/glyph_vt.py) for the manager's text surface,
and the item-29 containment fence + reaper (tools/glyph_containment.py).
Kernel-class host manipulation of guest RAM has landed precedent:
item-40 _seed_tray / harvest (glyph_notify.py:313-349). Pure consumer —
NO new syscall number, no engine change, no edits to any landed tool
module.

Design contract (the honest shape of "signals" on the cooperative
model): there is NO preemption and NO mid-run interrupt — a RUNNING
task cannot be signalled (glyph_process.py:198-199 refuses re-entry;
that refusal is landed behavior and stays). kill/pause therefore act
BEFORE first run or AFTER a run boundary, kernel-class:

  - pause(pid): state -> "paused". A paused task is skipped by
    GlyphTaskManager.run_ready() and cannot be waited to completion.
  - resume(pid): state -> "ready" (only from "paused"; loud otherwise).
  - kill(pid): for a task that has NOT run: reaped-without-running —
    state "exited", exit_status EXIT_FAULT (SIGKILL-analog: no guest
    code ever executes, by construction — the strongest possible
    guarantee and honestly stated as such). For an ALREADY-REAPED
    window's task it is a no-op raise (already exited).
  - Clean window close: manager.close_window(wid) retires a REAPED
    window via comp.set_visible(wid, False) (the compositor's
    append-only sanctioned removal, item-40 expire idiom) and drops the
    manager's bookkeeping; close on a non-reaped window is REFUSED
    loud (a running task's tile is live).

The task manager tile is a real fenced compositor window whose guest
task paints a per-pid STATE BAR from kernel-seeded words (item-40 tray
idiom): one row per task, a filled color cell per state (green ready,
amber paused, red exited-fault, dim exited-ok), painted by the guest
from its OWN tile origin via the TILE_ROW/COL idiom. A refresh respawns
the manager task at the SAME locked rect with freshly seeded state
words (glyph_notify.py:_repaint_tray shape).

## Scope (positive)

- NEW: tools/glyph_taskmgr.py — GlyphTaskManager over
  GlyphCompositor + GlyphProcessTable contracts: pause/resume/kill
  (kernel-class, run-boundary semantics per the design contract),
  run_ready() (advance every ready task one cooperative run, skipping
  paused), open_manager() manager-tile placement + seed_tasks()
  kernel-class state-word seeding, refresh() respawn-repaint at the
  locked rect, close_window() clean reaped-window close, tasks()
  introspection snapshot.
- NEW: tests/test_item41_taskmgr.py — the gate below.
- NEW: .builder_queue/RECEIPT_item41_taskmgr.md
- Ledger: .builder_queue/PRODUCT_LANE_STATE.md (dated section),
  .builder_queue/QUEUE_STATE.json (item-41 -> landed + commit),
  .builder_queue/CURRENT_TICKET.json (reconciled).

## Scope (negative — must not touch)

- tools/glyph_isa_v2.py and any engine/WGSL file (no new syscall;
  N1 byte-guard pins glyph_isa_v2.py md5 = 5a672d7d5a94a7b20f927f554b8a90c0).
- tools/glyph_compositor.py, glyph_process.py, glyph_stratum.py,
  glyph_containment.py, glyph_shell.py, glyph_vt.py, glyph_channel.py,
  glyph_notify.py — every landed item-10..40 module (pure-consumer
  contract; the process table's cooperative refusal and the
  compositor's append-only records are USED, never overridden — no
  monkey-patching, no subclass override of GlyphProcessTable._run_task).
- Protected assets (voicebook/, .rts/, rs_fixtures.json).

## Gate command

PYTHONPATH=. python3 -m pytest tests/test_item41_taskmgr.py -q
Expected exit 0; 10 legs stated in the gate clause.

## Gate clause

GREEN requires ALL of:

1. T1 Spawn + lifecycle table: the manager wraps comp.place() windows;
   a fresh placement is state "ready"; run_ready() advances it to
   "exited" with the task's own exit status (a HALT-only guest ->
   EXIT_OK); tasks() reports pid/wid/name/state/exit_status accurately
   for at least two concurrent windows.
2. T2 Kill-before-run: kill(pid) on a task that has NOT run reaps it
   "exited"/EXIT_FAULT WITHOUT any guest execution (its PRT output
   stream is EMPTY — proof no instruction ran); comp.composite() shows
   no paint from the killed window's tile (never placed a run).
3. T3 Pause/resume: pause(pid) on a ready task -> "paused";
   run_ready() leaves it paused and runs OTHER tasks; resume(pid) ->
   "ready"; the next run_ready() then completes it. resume() on an
   exited pid raises loud; pause() on an unknown pid raises loud.
4. T4 Kill-after-reap refuses: kill() on an already-exited task raises
   loud and the task's recorded exit_status/state are unchanged.
5. T5 Manager tile end-to-end: open_manager() places a real fenced
   window; with one ready, one paused, and one exited-fault (killed)
   task, the manager guest paints a distinct state-cell color per row
   from SEEDED words at its own tile origin (composite readback:
   green/amber/red rows present, dim row for exited-ok); hit_test
   inside the tile returns the manager wid.
6. T6 Refresh respawn: after changing a task's state, refresh() respawns
   the manager task at the SAME locked rect (the new manager window's
   rect equals the old one) and the composite shows the NEW state color
   at that task's row (the reactive leg — item-40 T5 pattern).
7. T7 Clean window close: close_window(wid) on a REAPED window retires
   it — comp.hit_test() in its tile returns None (or the underlying
   window), composite() no longer shows its paint, and the manager's
   tasks() drops the association. close_window() on a NON-reaped
   (never-run) window is REFUSED loud and the window record is
   unchanged.
8. T8 Fence still governs: a rogue guest ordered to ST outside its own
   tile during a manager-driven run_ready() is reaped EXIT_FAULT
   (E-K1 + reaper), the manager records the fault, and the other
   tasks' lifecycle operations still work afterwards.
9. N1 Engine byte-guard: glyph_isa_v2.py md5 ==
   5a672d7d5a94a7b20f927f554b8a90c0 (no engine change).
10. N2 Non-vacuity: with ZERO tasks, run_ready() returns an empty
    result and the manager tile paints only its header/no task rows
    (seeded all-zero state words paint nothing per-row); pause() on a
    pid that never existed raises (a gate that cannot fail is
    decoration).

Leg count: 10 legs (T1..T8 + N1 + N2). GREEN = 10 passed, exit 0.

## Failure evidence (RED first)

Before landing: (RED 1) make run_ready() IGNORE the paused state (run
paused tasks like ready ones) — T3 MUST fail; (RED 2) make kill() on a
not-yet-run task mark exit_status EXIT_OK instead of EXIT_FAULT — T2
MUST fail (its PRT-empty + EXIT_FAULT assertion). Both REDs
demonstrated as failing legs on the mutated tree before GREEN is
trusted; mutations reverted before GREEN (diff-confirmed, md5
asserted). A GREEN without demonstrated REDs is not evidence.

## Failure protocol

Interfaces are LOCKED: GlyphProcessTable cooperative semantics (the
running-task re-entry refusal, state machine, EXIT_OK/EXIT_FAULT),
compositor place/move/set_visible semantics and append-only records,
containment fence + reaper contract, assembler mnemonics and the
TILE_ROW/COL paint idiom, engine MMIO addresses. If a locked contract
blocks a leg, file REPAIR_PENDING_item41_<topic>.md with 2-4 options
cheapest-first and pick the next eligible unit — never weaken a live
guard to pass.

## Definition of done

RED tails + GREEN tail pasted literally in the receipt; ledger +
QUEUE_STATE + CURRENT_TICKET updated; single commit containing ONLY
the in-scope files (force-add tests/ past .gitignore).
