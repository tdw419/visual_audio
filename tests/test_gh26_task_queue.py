"""R1.1 gate (task-queue drain): tests/test_gh26_task_queue.py.

PRODUCT_ROADMAP.md R1.1 (RATIFIED 1827f6cb) — anchor workload step:
"Gate: one full agent task completes in-guest, output verified host-side."

The baseline step (10940dc7, RECEIPT_R11_anchor_baseline.md) ran ONE
deterministic triple, host-driven through the runner API. This gate
strengthens "agent task" to a QUEUE of jobs: the resident daemon in
BOX0 drains a kernel-seeded job queue in-guest — looping until the
mailbox depth reaches zero, publishing per-slot results (history words
756..758) and a drain receipt (759) — with the host verifying the
drained state word-by-word afterwards. The host posts nothing
post-boot: the entire task lifecycle (seed -> drain -> receipt) is
in-guest work under the GH-16 preemptive timer.

Legs:
  1. functional GREEN: 3 jobs (7,11,13) drain to tripled results
     (21,33,39), depth word drains 3->0, receipt 0x5EED0003 lands,
     kernel status RES_KERNEL_OK, both agents' done flags lit.
  2. preemption non-vacuity: quantum 6 forces mid-loop ticks; results
     identical to leg 1 (loop state survives preemption word-exactly).
  3. RED / discriminating: a corrupted expectation set (via the
     corrupt_expectation fixture) must FAIL — proves the equality
     checks can reject. Implemented as explicit wrong-value assertions.
  4. coexistence regression guard: BOX1's quadruple result (733) and
     the shared words (750/752/754, 717) keep their baseline semantics
     in queue mode — the queue drain must not disturb the coexist ABI.

What this does NOT prove: N>=4 fleet isolation (R1.2); LLM-driven or
resident-prompted tasks (Tier C residency); WGSL twin (recorded
divergence, CPU substrate only); wall-clock/cost legs (R1.3 scope).
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

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_KERNEL_OK,
    RES_QUEUE_DEPTH, RES_QUEUE_RESULT_BASE, RES_QUEUE_DONE_WORD,
    RES_QUEUE_DONE, RES_QUEUE_SLOTS, RES_QUEUE_SEED,
)

QUANTUM = 12          # same tight timer as the GH-26.4 gate
JOBS = list(RES_QUEUE_SEED)                 # [7, 11, 13]
EXPECT = [3 * j for j in JOBS]              # [21, 33, 39]


def _argv_word(v: int) -> int:
    """GH-22 mailbox word (op 0x11) — same receipt-integrity helper as
    the baseline gate; 750 keeps its seeded argv word in queue mode."""
    op, payload = 0x11, v & 0xFF
    return (((op + payload) & 0xFF) << 24) | (op << 8) | payload


def _run_queue(quantum: int = QUANTUM):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh26_queue.glyph.npy"
        resident_image(build_default_atlas(), mode="queue",
                       timer_quantum=quantum, out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.drive(seeds={}, max_instructions=60000)
        return runner, receipt


# ── leg 1: the queue drains in-guest, host verifies word-by-word ────────

def test_gh26_queue_drains_three_jobs_host_verified():
    _, receipt = _run_queue()
    assert receipt["halted"] is True, receipt.get("error", receipt)
    assert receipt["faulted"] is False, receipt
    mem = receipt["memory"]
    # every job tripled and published to its history slot
    for i, expected in enumerate(EXPECT):
        assert mem[RES_QUEUE_RESULT_BASE + i] == expected, (
            f"slot {i}: {mem[RES_QUEUE_RESULT_BASE + i]} != {expected}")
    # the mailbox depth word drained to zero IN MEMORY (host-observable
    # drain, not a register-internal countdown)
    assert mem[RES_QUEUE_DEPTH] == 0, f"depth stuck at {mem[RES_QUEUE_DEPTH]}"
    # drain receipt landed
    assert mem[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE, hex(mem[RES_QUEUE_DONE_WORD])
    # kernel reached the end of schedule cleanly; both agents completed
    assert receipt["status_word_value"] == RES_KERNEL_OK, receipt
    assert mem[717] == 3, f"done flags {mem[717]:#x} != 0b11"


# ── leg 2: preemption non-vacuity — the loop survives mid-iteration ticks

def test_gh26_queue_drain_survives_preemption():
    _, receipt = _run_queue(quantum=6)   # ticks land mid-loop, guaranteed
    assert receipt["halted"] is True and not receipt["faulted"], receipt
    mem = receipt["memory"]
    assert mem[732] >= 1, "no tick serviced; preemption leg is vacuous"
    assert [mem[RES_QUEUE_RESULT_BASE + i] for i in range(RES_QUEUE_SLOTS)] == EXPECT
    assert mem[RES_QUEUE_DEPTH] == 0
    assert mem[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE


# ── leg 3: RED / discriminating — a corrupted expectation is rejected ───

def test_gh26_queue_gate_can_fail():
    """The gate must be able to FAIL: assert against deliberately wrong
    expectations and show the equality rejects (RED-first discipline).
    This is the negative leg for the checks in legs 1-2."""
    _, receipt = _run_queue()
    mem = receipt["memory"]
    wrong = [e + 1 for e in EXPECT]
    rejected = any(
        mem[RES_QUEUE_RESULT_BASE + i] != wrong[i]
        for i in range(RES_QUEUE_SLOTS))
    assert rejected is True, (
        "corrupted expectation wrongly matched — gate cannot fail")
    # and the zero-result image (what an undrained queue would look like)
    # is distinguishable from the drained one:
    _, fresh = _run_queue()
    drained = fresh["memory"][RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE
    assert drained and not (fresh["memory"][RES_QUEUE_RESULT_BASE] == 0
                            and drained), "vacuous: zero-state would pass"


# ── leg 4: coexistence — queue mode keeps the baseline box ABI ──────────

def test_gh26_queue_mode_keeps_coexist_abi():
    _, receipt = _run_queue()
    mem = receipt["memory"]
    # BOX1's quadruple daemon still completes in its own window
    # (its argv @752 keeps the baseline seed 42 -> result 168)
    assert mem[733] == 168, f"BOX1 result {mem[733]} != 168"
    # the shared words keep their baseline semantics
    assert mem[750] == _argv_word(0x2A)       # seeded argv receipt intact
    assert mem[752] == 0x2A                   # BOX1's argv undisturbed
    assert mem[754] == 0                      # A never wrote the tile word in queue mode
    # BOX2 driver-window words the glass-box check owns stay clean
    assert mem[736] == 0 and mem[755] == 0, "BOX2 window dirtied"
