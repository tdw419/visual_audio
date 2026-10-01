"""pytest plugin — DEFECT-18 option (a) prototype: engine-side USER regfile
snapshot/restore across a preemptive tick.

Parked decision (do NOT auto-implement): .builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md
Option (a) reads "the engine snapshots the USER register file on a tick and restores
it when the handler returns to USER mode" — same machinery the SYSCALL trap already
uses (tools/glyph_isa_v2.py:843 `_syscall_regs = self.registers[:]`, :865 restore).

This plugin measures that option WITHOUT touching the tracked engine: it wraps
GlyphCPUv2.step and, when the GH-16 tick block fires (TICK_PC_ADDR word changes),
snapshots the register file; when execution resumes at the interrupted PC (the
handler's JMPR target = the word the engine parked in TICK_PC), it restores the
snapshot and re-enters USER mode.

Evidence only — no engine file is modified, nothing is committed.

Enable:  PYTHONPATH=.builder_queue python3 -m pytest ... -p plugin18a_tick
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))

from glyph_isa_v2 import (  # noqa: E402
    GlyphCPUv2,
    INSTR_WIDTH,
    MODE_USER,
    TICK_PC_ADDR,
)

_stats = {"ticks": 0, "restores": 0}
_orig_step = GlyphCPUv2.step


def _step(self, image):
    snap = getattr(self, "_opta_regs", None)
    if snap is not None:
        col = self.pc[0] // INSTR_WIDTH
        packed_now = ((self.pc[1] & 0xFFFF) << 16) | (col & 0xFFFF)
        if packed_now == getattr(self, "_opta_pc", None):
            # The kernel handler jumped back to the interrupted USER PC: put the
            # USER register file back and re-enter USER mode (option (a)).
            self.registers[:] = snap
            self.mode = MODE_USER
            self._opta_regs = None
            _stats["restores"] += 1

    idx = TICK_PC_ADDR >> 2
    before = self.memory[idx] if len(self.memory) > idx else 0
    rc = _orig_step(self, image)
    after = self.memory[idx] if len(self.memory) > idx else 0
    if after != before:
        # GH-16 tick delivered: user state is intact right now (the handler has
        # not executed yet) — this is the snapshot point.
        self._opta_regs = self.registers[:]
        self._opta_pc = after
        _stats["ticks"] += 1
    return rc


GlyphCPUv2.step = _step


def pytest_report_header(config):
    return (f"plugin18a_tick: DEFECT-18 option (a) PROTOTYPE active — "
            f"ticks_seen={_stats['ticks']} regfile_restores={_stats['restores']} "
            f"(counters are live; see the end-of-run line)")


def pytest_sessionfinish(session, exitstatus):
    print(f"\nplugin18a_tick: ticks_delivered={_stats['ticks']} "
          f"regfile_restores={_stats['restores']} "
          f"(restores==ticks means every tick was made transparent)")
