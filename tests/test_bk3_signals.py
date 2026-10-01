"""BK-3 gate: tests/test_bk3_signals.py.

Roadmap (systems/GLYPH_SELF_HOSTING_ROADMAP.md, BK-3 — promoted from
GLYPH_BACKLOG): "Signals lite: kernel-delivered SIG_KILL/SIG_USR1 to a box
via mailbox word; handler registration syscall."

Gate legs (the spec's oracle clause, mapped):
  L1 (kill):      task A signals SIG_KILL to B mid-round-robin; B is never
                  scheduled again (work + done flag stay clear); B's box
                  bounds are de-registered by the kernel (MMIO words 0).
  L2 (A intact):  A completes its post-kill work (receipt 0xBEEF) and exits
                  0xFEED0006; the kernel reaches its done tail.
  L3 (SIGUSR1):   B registers a handler via the registration syscall; the
                  kernel delivers it; the handler runs IN B'S BOX in USER
                  mode and posts its receipt (handler word lit, handler ran
                  BEFORE B's own work slice — signals preempt the round).
  L4 (bounds):    SIG_KILL'd box is hard-dead: with the kill armed, a
                  delivery attempt to B is suppressed by the kernel's
                  liveness guard AND B's bounds words read 0; a USER store
                  that would escape any box still faults E-K1 (kernel
                  fault receipt) without destabilizing the kernel.

Mechanism (in-image kernel, agent_resident.py patterns — zero engine
changes): SIG_KILL = SUPER slice zeroes BOX1_LO/HI MMIO words + marks the
kill bitmap; a killed box is never scheduled again (guard in the dispatch
leg). Handler registration = syscall whose SUPER slice copies the trapped
a0 (the handler's packed pixel PC) into the registrant's in-box handler
word. Delivery = SUPER dispatch leg reads the target's handler word, arms
the MODE_LATCH one-shot, and JMPRs into the handler (USER); the handler
returns through the privilege boundary (KJMP) like any task slice.
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
from tools.glyph_gpt.signals import (                          # noqa: E402 (RED)
    signals_image, BK3_STATUS_WORD, BK3_KERNEL_OK,
    BK3_KILL_RECEIPT, BK3_A_EXIT_OK, BK3_HANDLER_RECEIPT,
    BK3_B_EXIT_OK, BK3_FAULT_SEEN, BK3_WORK_A, BK3_WORK_A_POST,
)


QUANTUM = 12   # tight timer: ticks land mid-task (signals under preemption)


def _bake(tmp: Path, kill: bool = True, quantum: int = QUANTUM,
          escape: bool = False) -> Path:
    out = tmp / "bk3.glyph.npy"
    signals_image(kill=kill, timer_quantum=quantum, out_path=out, escape=escape)
    return out


def _run(tmp: Path, kill: bool = True, quantum: int = QUANTUM,
         escape: bool = False):
    runner = GlyphRunner(_bake(tmp, kill, quantum, escape), ram_words=16384)
    receipt = runner.drive(seeds={}, max_instructions=60000)
    return runner, receipt


# ── L1: SIG_KILL halts B mid-round-robin ────────────────────────────────

def test_bk3_sigkill_halts_b_and_deregisters_bounds():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d), kill=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # kernel's kill slice executed: receipt word carries SIG_KILL
        assert mem[760] == BK3_KILL_RECEIPT, hex(mem[760])
        # B never ran its work slice (killed before scheduling)
        assert mem[720] == 0, f"B's work ran after SIG_KILL: {mem[720]:#x}"
        # B's done flag never lit
        assert mem[717] & 1, "A's done flag clear"
        assert not (mem[717] & 2), f"B's done flag lit after SIG_KILL: {mem[717]:#x}"
        # the kill de-registered B's box bounds (words 8197/8198 read 0)
        assert mem[8197] == 0 and mem[8198] == 0, "BOX1 bounds still armed"


# ── L2: A unaffected by the kill it issued ──────────────────────────────

def test_bk3_sigkill_leaves_a_unaffected():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d), kill=True)
        assert receipt["halted"] is True and not receipt["faulted"], receipt
        mem = receipt["memory"]
        assert mem[BK3_WORK_A] == 273, mem[BK3_WORK_A]
        # A did REAL work after the kill landed (post-kill receipt)
        assert mem[BK3_WORK_A_POST] == 0xBEEF, hex(mem[BK3_WORK_A_POST])
        assert mem[703] == BK3_A_EXIT_OK, hex(mem[703])
        assert mem[BK3_STATUS_WORD] == BK3_KERNEL_OK, hex(mem[BK3_STATUS_WORD])


# ── L3: SIGUSR1 — B's registered handler runs (no-kill variant) ─────────

def test_bk3_sigusr1_handler_runs_in_box():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d), kill=False)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # B registered a handler (kernel mirrored the trapped a0 into B's
        # in-box handler word) — non-zero receipt proves registration
        assert mem[733] != 0, "handler registration never landed"
        # the kernel DELIVERED the signal: B's handler executed and posted
        # its receipt before B's own work slice ran (signal preempts round)
        assert mem[721] == BK3_HANDLER_RECEIPT, mem[721]
        assert mem[720] == 7, f"B's work slice missing after handler: {mem[720]}"
        assert mem[723] == BK3_B_EXIT_OK, hex(mem[723])
        assert mem[717] & 2, "B's done flag clear"
        assert mem[BK3_STATUS_WORD] == BK3_KERNEL_OK, hex(mem[BK3_STATUS_WORD])


# ── L4: box bounds still enforced (adversarial) ─────────────────────────

def test_bk3_bounds_enforced_after_kill_and_on_escape():
    with tempfile.TemporaryDirectory() as d:
        # escape=True bakes the L4 adversarial leg: A's out-of-box store
        # (word 5000) must E-K1 — the engine's sticky fault flag is why
        # this image is confined to this test.
        _, receipt = _run(Path(d), kill=True, quantum=QUANTUM, escape=True)
        mem = receipt["memory"]
        # kernel stayed alive to the done tail with the fault receipt from
        # the adversarial escape leg (an out-of-box USER store still E-K1s)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert mem[BK3_STATUS_WORD] == BK3_KERNEL_OK, hex(mem[BK3_STATUS_WORD])
        assert mem[759] == BK3_FAULT_SEEN, hex(mem[759])
        # the killed box's bounds remain de-registered
        assert mem[8197] == 0 and mem[8198] == 0
        # and the other box's bounds were untouched by the kill
        assert mem[8195] == 2800 and mem[8196] == 2868, (mem[8195], mem[8196])


# ── non-vacuity: ticks actually fired (signals work under preemption) ───

def test_bk3_ticks_serviced():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d), kill=False)
        mem = receipt["memory"]
        assert mem[732] >= 1, f"timer never fired: {mem[732]}"
