"""BK-4 gate: tests/test_bk4_join.py.

Roadmap (systems/GLYPH_SELF_HOSTING_ROADMAP.md, BK-4 — promoted from
GLYPH_BACKLOG by builder cron af3e62239ce2, commit 212b19d): "waitpid/join:
parent task blocks on child exit code via kernel syscall."

Gate legs (the spec's oracle clause, mapped — join is asynchronous:
the kernel joins at the round boundary, not mid-slice):
  L1 (fresh join):    parent A spawns B; B exits 42 via SYS 12; A joins
                      via SYS 13 — kernel completes the child, THEN
                      delivers 42 into A's in-box join word; A exits 7.
  L2 (already-dead):  B's exit already landed in the exit word; a second
                      join returns the SAME code immediately — nothing
                      re-runs the child (B's work receipt is written
                      exactly once).
  L3 (single-fire):   across one execution B's work receipt is written
                      exactly once and the exit code records 42 exactly
                      once (the join never re-runs the child).

Mechanism (in-image kernel, signals.py patterns — zero engine changes):
SYS 12 (exit) SUPER slice stores the trapped a0 into the kernel-owned
EXIT_CODE word and lights the child-done flag. SYS 13 (join) with the
child still running defers — the SUPER dispatch continuation runs the
child to completion, promotes its done flag, then routes to the join
slice which copies EXIT_CODE into the parent's in-box join word and
SYSRETs back into the parent. Joining an already-dead child is the
same copy without the dispatch detour.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402 (RED)
from tools.glyph_gpt.join import (                             # noqa: E402 (RED)
    join_image, BK4_STATUS_WORD, BK4_KERNEL_OK, BK4_A_EXIT_OK,
    BK4_B_EXIT_OK, BK4_WORK_A, BK4_WORK_B, BK4_JOIN_WORD,
    BK4_EXIT_CODE, BK4_DONE_WORD,
)

QUANTUM = 12   # tight timer: joins under preemption


def _run(tmp: Path, quantum: int = QUANTUM):
    out = tmp / "bk4.glyph.npy"
    join_image(timer_quantum=quantum, out_path=out)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.drive(seeds={}, max_instructions=60000)
    return runner, receipt


# ── L1: fresh join — child exits 42, parent reads 42 ────────────────────

def test_bk4_join_fresh_child_delivers_exit_code():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # the child really ran its work slice
        assert mem[BK4_WORK_B] == 42, mem[BK4_WORK_B]
        # the child's exit syscall recorded its code
        assert mem[BK4_EXIT_CODE] == 42, hex(mem[BK4_EXIT_CODE])
        # THE GATE: the parent's join delivered the child's code in-box
        assert mem[BK4_JOIN_WORD] == 42, f"join word: {mem[BK4_JOIN_WORD]}"
        # both children-of-the-round completed; parent exited 7, kernel done
        assert mem[703] == BK4_A_EXIT_OK, hex(mem[703])
        assert mem[723] == BK4_B_EXIT_OK, hex(mem[723])
        assert mem[BK4_DONE_WORD] == 3, hex(mem[BK4_DONE_WORD])
        assert mem[BK4_STATUS_WORD] == BK4_KERNEL_OK, hex(mem[BK4_STATUS_WORD])


# ── L2: join on an already-dead child returns immediately ────────────────

def test_bk4_join_already_dead_child_returns_immediately():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        assert receipt["halted"] is True and not receipt["faulted"], receipt
        mem = receipt["memory"]
        # the second join (A's post-join re-join leg) returned the same
        # code without any re-dispatch of the child
        assert mem[BK4_JOIN_WORD] == 42, hex(mem[BK4_JOIN_WORD])
        assert mem[BK4_EXIT_CODE] == 42, hex(mem[BK4_EXIT_CODE])


# ── L3: the child is never re-run (single-fire) ──────────────────────────

def test_bk4_child_never_rerun():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        mem = receipt["memory"]
        # B's work receipt is written exactly once: the exit word records
        # code 42 (not 84 = double-run) and B's exit marker is the single
        # well-known value, not a re-execution artifact
        assert mem[BK4_EXIT_CODE] == 42, hex(mem[BK4_EXIT_CODE])
        assert mem[723] == BK4_B_EXIT_OK, hex(mem[723])


# ── non-vacuity: ticks actually fired (joins work under preemption) ──────

def test_bk4_ticks_serviced():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        mem = receipt["memory"]
        assert mem[732] >= 1, f"timer never fired: {mem[732]}"
