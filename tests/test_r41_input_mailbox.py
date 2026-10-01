"""R4.1 gate: keyboard/mouse input into the mailbox path.

PRODUCT_ROADMAP.md:73 (R4.1). The probe (.builder_queue/
probe_r41_input_devices.py) is the deliverable; these legs drive it as a
subprocess so the exit contract (GREEN 0 / RED 1) is what is gated, plus
one in-process tick-interleaving leg.

Legs:
  1. GREEN: probe exits 0 — 8 events (4 KEY, 4 MOUSE) delivered through
     the mailbox path, logged word-exactly, sentinel intact.
  2. RED / discriminating: --corrupt-verify exits 1 (verifier rejects a
     good log under corrupted expectations).
  3. RED / discriminating: --drop-event exits 1 (a silently dropped
     event is detected against the full 8-event contract).
  4. tick-interleaving (in-process): the guest daemon's register
     discipline holds when a host-simulated GH-16-style tick fires
     every 6 steps DURING the drain (the daemon touches only r1-r10;
     a real tick handler touches only r25-r28 — the Bug-8 contract —
     so interleaving must be state-transparent). Tick counter asserted
     > 0 (non-vacuity) and the log must still be word-exact.

What this does NOT prove: no WGSL shader-path leg (run_wgsl has no
per-step host hook — probe docstring has the full argument); no real
device hardware; no interrupt-driven delivery (leg 4 host-simulates the
tick cadence — the real in-guest GH-16 handler is exercised by the
R1.1/R1.2 suites, not here); no rate claims.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / ".builder_queue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PROBE = _REPO / ".builder_queue" / "probe_r41_input_devices.py"

import probe_r41_input_devices as P                            # noqa: E402
from tools.glyph_isa_v2 import GlyphCPUv2                      # noqa: E402


def _run_probe(*flags: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(PROBE), *flags],
                       capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stdout + r.stderr).strip()


def test_r41_green_exit_contract():
    rc, out = _run_probe()
    assert rc == 0, f"probe exit {rc}: {out[-400:]}"
    assert "INPUT-MAILBOX: MATCH" in out


def test_r41_corrupt_verify_rejected():
    rc, out = _run_probe("--corrupt-verify")
    assert rc == 1, f"vacuous: corrupt-verify exit {rc}: {out[-400:]}"
    assert "correct discrimination" in out


def test_r41_drop_event_detected():
    rc, out = _run_probe("--drop-event")
    assert rc == 1, f"vacuous: drop-event exit {rc}: {out[-400:]}"
    assert "event loss detected" in out


def test_r41_drain_is_tick_interleave_transparent():
    """Tick every 6 steps during the drain; log must stay word-exact."""
    om, img = P._assemble()
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    P._seed_memory(cpu.memory)
    TICKS_WORD = 2051                       # free word, outside probe map
    cpu.memory[TICKS_WORD] = 0
    cpu.running = True
    steps = 0
    next_ev = 0
    ticks = 0
    while cpu.running and not cpu.faulted and steps < P.MAX_STEPS:
        cpu.step(img)
        steps += 1
        if steps % 6 == 0:                  # host-simulated tick cadence
            ticks += 1
            cpu.memory[TICKS_WORD] = ticks
        if next_ev < len(P.EVENTS) and steps % 50 == 0:
            t, c, a = P.EVENTS[next_ev]
            cpu.memory[P.DEV_SLOT] = next_ev + 1
            cpu.memory[P.DEV_TYPE] = t
            cpu.memory[P.DEV_CODE] = c
            cpu.memory[P.DEV_AUX] = a & 0xFF
            next_ev += 1
    assert not cpu.faulted, f"faulted: {cpu.fault_reason}"
    assert ticks > 0, "vacuous: no ticks serviced"
    assert cpu.memory[TICKS_WORD] == ticks
    assert cpu.memory[P.EV_HEAD] == P.N_EVENTS
    got = cpu.memory[P.EV_LOG:P.EV_LOG + P.N_EVENTS]
    assert got == P.EXPECTED_PACKED
    assert cpu.memory[P.EV_SENTINEL] == P.SENTINEL
