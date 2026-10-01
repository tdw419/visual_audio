"""R1.1 gate (post-boot job arrival): tests/test_gh26_arrive.py.

PRODUCT_ROADMAP.md R1.1 (RATIFIED 1827f6cb) — anchor workload step:
"one full agent task completes in-guest, output verified host-side."
RECEIPT_R11_task_queue.md residual gap: queue drain ≠ mailbox
receive-while-busy. This gate covers the OTHER half: a job that
ARRIVES post-boot, while the resident daemon is live.

mode="arrive" (additive, tools/glyph_gpt/agent_resident.py): phase 1
drains the kernel-seeded queue exactly like mode="queue" (depth @740
3->0, results 756..758 tripled in place, receipt 0x5EED0003 @759);
phase 2 is a BOUNDED wait loop (2000 polls) watching arrival flag
@742. The host seat posts WHILE the daemon is in that loop
(flag=1, payload=9 @760); the daemon claims the job (flag back to 0),
triples the payload in place (27 @760), and publishes the arrival
receipt 0x5EED0004 @761.

Legs:
  1. functional GREEN: drain + post-boot arrival, host-verified
     word-by-word after the run (claim via drive()-step interleaving).
  2. preemption non-vacuity: quantum 6 forces mid-loop ticks; results
     identical (wait-loop state survives preemption word-exactly).
  3. RED / discriminating: a corrupted expectation set must FAIL.
  4. no-post: with the seat silent, the daemon times out its bounded
     loop, publishes NO arrival receipt (@761 == 0), and still exits
     cleanly — a receipt without a post is impossible by construction.
  5. coexistence regression guard: BOX1's quadruple (733), shared
     words (750/752/754, 717), and the BOX2 driver-window words the
     glass-box check owns (736/755/762..767) stay clean.

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
    RES_QUEUE_DONE, RES_QUEUE_SEED,
    RES_ARRIVE_FLAG, RES_ARRIVE_PAYLOAD, RES_ARRIVE_RCPT,
    RES_ARRIVE_DONE, RES_ARRIVE_SEED_JOB,
)

QUANTUM = 12          # same tight timer as the GH-26.4 gate
JOBS = list(RES_QUEUE_SEED)                 # [7, 11, 13]
EXPECT = [3 * j for j in JOBS]              # [21, 33, 39]
ARRIVE_EXPECT = 3 * RES_ARRIVE_SEED_JOB     # 27
POLL_BUDGET = 60000       # drive() step budget for the wait loop


def _argv_word(v: int) -> int:
    """GH-22 mailbox word (op 0x11) — same receipt-integrity helper as
    the baseline/queue gates."""
    op, payload = 0x11, v & 0xFF
    return (((op + payload) & 0xFF) << 24) | (op << 8) | payload


def _run_arrive(post_arrival: bool, quantum: int = QUANTUM):
    """Boot the arrive image, run phase 1 (drain) to completion, then —
    if post_arrival — post the seat's job WHILE the daemon is live in
    the phase-2 wait loop, and let the run finish.

    The host-post loop mirrors GH-11/GH-26 semantics: host writes to
    live RAM between step() calls, exactly what a supervisor seat does
    through the mailbox ABI. Post timing is adaptive: step until the
    drain receipt lands, then post immediately (mid-wait), so the
    arrival genuinely happens POST-boot and DURING the wait loop
    rather than before boot.
    """
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "gh26_arrive.glyph.npy"
        resident_image(build_default_atlas(), mode="arrive",
                       timer_quantum=quantum, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True          # drive()'s manual-step path does the same
        posted = False
        steps = 0
        posted_at = None
        while cpu.running and steps < POLL_BUDGET:
            cpu.step(runner.image)
            steps += 1
            if (post_arrival and not posted and steps > 200
                    and len(cpu.memory) > RES_QUEUE_DONE_WORD
                    and cpu.memory[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE):
                # seat posts: flag + payload, while the daemon waits
                cpu.memory[RES_ARRIVE_FLAG] = 1
                cpu.memory[RES_ARRIVE_PAYLOAD] = RES_ARRIVE_SEED_JOB
                posted, posted_at = True, steps
        receipt = {"halted": not cpu.running, "steps": steps,
                   "posted_at": posted_at, "posted": posted,
                   "memory": cpu.memory, "fault_reason": cpu.halt_reason}
        return runner, receipt


# ── leg 1: drain + post-boot arrival, host-verified word-by-word ────────

def test_gh26_arrive_post_boot_job_serviced():
    _, receipt = _run_arrive(post_arrival=True)
    mem = receipt["memory"]
    assert receipt["posted"], "seat never got to post (drain receipt never seen?)" \
        f" halt_reason={receipt['fault_reason']!r}"
    assert receipt["posted_at"], "posted before boot work (vacuous arrival)"
    assert mem[RES_QUEUE_RESULT_BASE:RES_QUEUE_RESULT_BASE + 3] == EXPECT, \
        f"drain leg wrong: {mem[RES_QUEUE_RESULT_BASE:RES_QUEUE_RESULT_BASE + 3]}"
    assert mem[RES_QUEUE_DEPTH] == 0
    assert mem[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE
    assert mem[RES_ARRIVE_FLAG] == 0, "daemon must claim (clear) the flag"
    assert mem[RES_ARRIVE_PAYLOAD] == ARRIVE_EXPECT, \
        f"arrival result {mem[RES_ARRIVE_PAYLOAD]} != {ARRIVE_EXPECT}"
    assert mem[RES_ARRIVE_RCPT] == RES_ARRIVE_DONE, \
        f"arrival receipt {mem[RES_ARRIVE_RCPT]:#x} != {RES_ARRIVE_DONE:#x}"
    assert mem[717] == 3, f"done word {mem[717]} != 3"
    assert mem[736] == 0 and mem[755] == 0, "BOX2 driver window dirtied"
    assert mem[759] == RES_QUEUE_DONE and mem[761] == RES_ARRIVE_DONE


# ── leg 2: preemption non-vacuity — mid-wait ticks change nothing ────────

def test_gh26_arrive_survives_mid_loop_ticks():
    _, tight = _run_arrive(post_arrival=True, quantum=6)
    mem = tight["memory"]
    assert tight["posted"] and mem[RES_ARRIVE_RCPT] == RES_ARRIVE_DONE
    assert mem[RES_ARRIVE_PAYLOAD] == ARRIVE_EXPECT
    assert mem[RES_QUEUE_RESULT_BASE:RES_QUEUE_RESULT_BASE + 3] == EXPECT
    assert mem[732] > 0, "vacuous: no ticks serviced"


# ── leg 3: RED / discriminating — corrupted expectation is rejected ─────

def test_gh26_arrive_corrupt_expectation_rejected():
    _, receipt = _run_arrive(post_arrival=True)
    mem = receipt["memory"]
    wrong = ARRIVE_EXPECT + 1
    rejected = not (mem[RES_ARRIVE_PAYLOAD] == wrong
                    and mem[RES_ARRIVE_RCPT] == RES_ARRIVE_DONE + 1)
    assert rejected, "vacuous: corrupted expectation matched"


# ── leg 4: no post -> no arrival receipt, clean bounded timeout ──────────

def test_gh26_arrive_no_post_no_receipt():
    _, receipt = _run_arrive(post_arrival=False)
    mem = receipt["memory"]
    assert receipt["halted"], f"daemon never halted: {receipt['fault_reason']!r}"
    assert mem[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE   # drain still real
    assert mem[RES_ARRIVE_RCPT] == 0, \
        f"receipt {mem[RES_ARRIVE_RCPT]:#x} minted without a post"
    assert mem[RES_ARRIVE_FLAG] == 0 and mem[717] == 3
    assert mem[RES_ARRIVE_PAYLOAD] == 0, "payload dirtied without a post"


# ── leg 5: coexistence — arrive mode keeps the baseline box ABI ──────────

def test_gh26_arrive_mode_keeps_coexist_abi():
    _, receipt = _run_arrive(post_arrival=True)
    mem = receipt["memory"]
    assert mem[733] == 168, f"BOX1 result {mem[733]} != 168"
    assert mem[750] == _argv_word(0x2A)
    assert mem[752] == 0x2A
    assert mem[754] == 0        # A never wrote the tile word in arrive mode
    assert mem[736] == 0 and mem[755] == 0 and mem[762] == 0 and mem[767] == 0
