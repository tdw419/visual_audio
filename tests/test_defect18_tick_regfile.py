#!/usr/bin/env python3
"""tests/test_defect18_tick_regfile.py — DEFECT-18 tick register-file snapshot/restore gate.

Roadmap row: DEFECT-18 in systems/GLYPH_SELF_HOSTING_ROADMAP.md.
Ruling: .builder_queue/RULING_20260912_defect18_a_defect17_d.md (Decision 1 -> Option (a)).
Ticket: .builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md.

Contracts verified:
- L1: Engine-level falsifier for DEFECT-18. A USER task holds live values in r25..r28
      when a timer tick is delivered. The armed tick handler clobbers all four registers,
      loads TICK_PC, and returns via JMPR. The engine must restore the snapshotted USER
      regfile and return to MODE_USER. On HEAD, this leg fails with clobbered values and
      MODE_SUPER (red-before-fix proof).
- L2: Loader/runner path parity leg. Byte-identical results with preemption on (timer_quantum=12)
      and off (timer_quantum=0) for a program driven through the GH-9 loader/runner path,
      with GH9_TICKS_COUNT >= 1 proving a tick fired during preemption.
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

from tools.glyph_isa_v2 import (
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
    INSTR_WIDTH,
    KTICK_PC_ADDR,
    TIMER_COUNT_ADDR,
    TIMER_RELOAD_ADDR,
    TICK_PC_ADDR,
    MODE_USER,
    MODE_SUPER,
)
from tests.test_bk1_argv import (
    _run_loader_online,
    GH9_ARGV_RESULT,
    GH9_TICKS_COUNT,
    GH9_EXIT_WORD,
    EXIT_OK,
)


def test_defect18_l1_engine_tick_regfile_snapshot_restore():
    """L1 (falsifier for DEFECT-18):
    The engine-level leg: a USER program holds distinct sentinel values live in
    r25/r26/r27/r28 when a tick is delivered; the armed handler clobbers all four;
    after the handler returns via JMPR, registers[25..28] must equal the sentinels
    and mode == MODE_USER.

    On HEAD, this leg FAILS because the engine leaves r25..r28 clobbered by the handler
    and leaves cpu.mode == MODE_SUPER.
    """
    cols_instrs = 16
    assembler = GlyphAssemblerV2(OpcodeMapV2())

    # Build program image:
    # Row 0: USER program (sets sentinels in r25..r28, ticks, resumes, halts)
    # Row 1: Tick handler (clobbers r25..r28, loads TICK_PC, returns via JMPR)
    user_lines = [
        "LDI r25 0x111111",      # col 0: sentinel r25
        "LDI r26 0x222222",      # col 1: sentinel r26
        "LDI r27 0x333333",      # col 2: sentinel r27
        "LDI r28 0x444444",      # col 3: sentinel r28 (timer fires here)
        "ADD r0 r0",             # col 4: resume point after tick
        "HALT",                  # col 5: finish
    ]
    user_lines += ["HALT"] * (cols_instrs - len(user_lines))

    tick_pc_word = TICK_PC_ADDR >> 2
    handler_lines = [
        "LDI r25 0x999925",      # col 0: scratch clobber r25
        "LDI r26 0x999926",      # col 1: scratch clobber r26
        "LDI r27 0x999927",      # col 2: scratch clobber r27
        "LDI r28 0x999928",      # col 3: scratch clobber r28
        f"LDI r25 {tick_pc_word}",  # col 4: load TICK_PC address
        "LD r25 r25",            # col 5: load packed interrupted PC
        "JMPR r25",              # col 6: return to interrupted USER PC
    ]
    handler_lines += ["HALT"] * (cols_instrs - len(handler_lines))

    all_lines = user_lines + handler_lines
    image = assembler.assemble(all_lines, width_instrs=cols_instrs)

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=cols_instrs)
    # Size memory past _ISO_TOP_WORD so _iso_enabled is True
    cpu.memory = [0] * 16384

    # Arm tick handler at row 1, col 0
    ktick_col = 0
    ktick_row = 1
    ktick_packed = (ktick_row << 16) | ktick_col
    cpu.memory[KTICK_PC_ADDR >> 2] = ktick_packed

    # Tick after 4 instructions (col 0, 1, 2, 3), so tick fires on the boundary
    # while r25..r28 hold the sentinel values
    cpu.memory[TIMER_COUNT_ADDR >> 2] = 4
    cpu.memory[TIMER_RELOAD_ADDR >> 2] = 1000

    # Start execution as USER at (0, 0)
    cpu.mode = MODE_USER
    cpu.pc = (0, 0)
    cpu.run(image, max_instructions=100)

    assert not cpu.faulted, f"CPU faulted at addr {cpu.fault_addr:#x}"
    assert not cpu.running, "CPU did not halt cleanly"

    # Verify that the tick was delivered to the handler and saved the interrupted PC (col 4, row 0)
    expected_interrupted_pc = (0 << 16) | 4
    assert cpu.memory[TICK_PC_ADDR >> 2] == expected_interrupted_pc, (
        f"TICK_PC word 0x{cpu.memory[TICK_PC_ADDR >> 2]:08x} != expected 0x{expected_interrupted_pc:08x}"
    )

    # R1/R2/R3: sentinels preserved across tick, and mode returned to MODE_USER
    assert cpu.registers[25] == 0x111111, (
        f"r25 clobbered across tick: 0x{cpu.registers[25]:08x} != 0x00111111"
    )
    assert cpu.registers[26] == 0x222222, (
        f"r26 clobbered across tick: 0x{cpu.registers[26]:08x} != 0x00222222"
    )
    assert cpu.registers[27] == 0x333333, (
        f"r27 clobbered across tick: 0x{cpu.registers[27]:08x} != 0x00333333"
    )
    assert cpu.registers[28] == 0x444444, (
        f"r28 clobbered across tick: 0x{cpu.registers[28]:08x} != 0x00444444"
    )
    assert cpu.mode == MODE_USER, (
        f"CPU mode not restored to MODE_USER after tick: mode={cpu.mode}"
    )


def test_defect18_l2_loader_preemption_parity():
    """L2: Byte-identical results with preemption ON and OFF for a program
    driven through the loader/runner path.

    Runs with timer_quantum=0 (preemption off) and timer_quantum=12 (preemption on).
    Verifies that GH9_TICKS_COUNT >= 1 in the preempted run and that GH9_ARGV_RESULT
    is bit-identical between the two runs.
    """
    op, payload = 0x11, 0x2A
    with tempfile.TemporaryDirectory() as td:
        # Run 1: preemption OFF (timer_quantum=0)
        runner_off, cpu_off = _run_loader_online(
            Path(td), op=op, payload=payload, timer_quantum=0, name="loader_off.npy"
        )
        assert not cpu_off.faulted, f"off faulted: addr={cpu_off.fault_addr:#x}"
        assert not cpu_off.running, "off execution must reach HALT"
        res_off = cpu_off.memory[GH9_ARGV_RESULT]
        assert cpu_off.memory[GH9_EXIT_WORD] == EXIT_OK

        # Run 2: preemption ON (timer_quantum=12)
        runner_on, cpu_on = _run_loader_online(
            Path(td), op=op, payload=payload, timer_quantum=12, name="loader_on.npy"
        )
        assert not cpu_on.faulted, f"on faulted: addr={cpu_on.fault_addr:#x}"
        assert not cpu_on.running, "on execution must reach HALT"
        ticks = cpu_on.memory[GH9_TICKS_COUNT]
        assert ticks >= 1, f"timer tick did not fire: ticks={ticks}"
        res_on = cpu_on.memory[GH9_ARGV_RESULT]
        assert cpu_on.memory[GH9_EXIT_WORD] == EXIT_OK

        # R5: Results must be byte-identical
        assert res_on == res_off, (
            f"preemption corrupted result: on=0x{res_on:08x} != off=0x{res_off:08x}"
        )
