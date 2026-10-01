"""item-29 gate: per-process spatial containment (spawn-allocated tiles).

Legs:
  B1  spawn(tile=...) arms the GO-2 tile words (TILE_ROW/COL/H/W) in the
      task's OWN memory and drops the engine to MODE_USER; an engine
      spawned WITHOUT a tile stays MODE_SUPER with TILE_H == 0 (inert) —
      the R1 migration invariant holds inside the same gate.
  B2  an in-tile user store LANDS: the word is written byte-exact and the
      task exits clean (exit_status == EXIT_OK, faulted stays False).
  B3  an out-of-tile user store TRAPS: the store does NOT land (target
      word unchanged), engine sets faulted, and the task maps to
      EXIT_FAULT via the table reaper.
  B4  REAPER leg: with reaper_pc armed, after the trap the engine is in
      MODE_SUPER parked on the reaper trampoline HALT (planted by the
      table in a tall copy of the image), FAULT_ADDR/FAULT_PC record the
      offending byte address / packed instr PC, the OFFENDING task (not
      its neighbor) carries EXIT_FAULT, and a containment-clean neighbor
      on the same table still exits EXIT_OK having written ITS tile.
  P5  tile bounds are the fence, not politeness: a store to the exact
      first word OUTSIDE the tile faults; a store to the exact LAST word
      INSIDE the tile lands (boundary semantics of [row, row+h) x
      [col, col+w)); zero-extent tiles are refused (no silent unfencing).
  R1  MIGRATION: item-26's P1 RAM-writer + EXIT-status contract re-run on
      this tree — no-tile spawn keeps the legacy behavior byte-for-byte.
  R2  MIGRATION: the item-26 gate itself re-runs GREEN in this tree via
      subprocess (the tile arm touches no process-table code path that
      item-26 pins).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to HEAD
      (item-29 is host-side arming of an existing engine contract; any
      engine drift invalidates the gate's premises).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (words, modes, statuses, fault registers). Zero new
syscall numbers; engine byte-unchanged (containment is armed from the
host-side table over the EXISTING GO-2 tile words + E-K1 trap path).
"""
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_containment import (  # noqa: E402
    DEFAULT_REAPER_ROW,
    ContainmentError,
    arm_tile,
    wrap_with_reaper,
)
from tools.glyph_isa_v2 import (  # noqa: E402
    FAULT_ADDR_ADDR,
    FAULT_PC_ADDR,
    GlyphAssemblerV2,
    GlyphCPUv2,
    KFAULT_PC_ADDR,
    MODE_SUPER,
    MODE_USER,
    OpcodeMapV2,
    TILE_COL_ADDR,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    TILE_W_ADDR,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessError, GlyphProcessTable  # noqa: E402

DATA_ADDR = 400   # above the program window (width 8 -> ~40 instrs used)

# The spawn-allocated tile: grid row 5, col 0, 2 rows x 4 cols. In word
# terms (W_MEM=32 words per grid row): the tile covers rows 5..6, cols
# 0..3 -> in-tile words {160..163, 192..195}. The in-tile probe uses word
# 160; the out-of-tile probe uses word 164 (same row band, col 4 — the
# first word outside) and word 400 (well outside).
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 164: first word outside


def _prog(lines):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def _ram_writer_prog(value: int, addr: int = DATA_ADDR) -> np.ndarray:
    """ST r6, r5 form: memory[r6]=r5, then HALT. The ST sits at
    instruction (row 0, col 2) -> FAULT_PC packs to (0<<16)|2."""
    return _prog([
        f"LDI r5 {value}",
        f"LDI r6 {addr}",
        "ST r6 r5",
        "HALT",
    ])


def _exit_prog(status: int) -> np.ndarray:
    return _prog([
        f"LDI r1 {status}",
        "SYSCALL r0 0x05",
        "HALT",
    ])


# ── B1: arming contract ──────────────────────────────────────────────────
def test_b1_spawn_arms_tile_and_user_mode():
    table = GlyphProcessTable()
    pid = table.spawn(_exit_prog(0), name="boxed",
                      tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    assert cpu.memory[TILE_ROW_ADDR >> 2] == TILE_ROW
    assert cpu.memory[TILE_COL_ADDR >> 2] == TILE_COL
    assert cpu.memory[TILE_H_ADDR >> 2] == TILE_H
    assert cpu.memory[TILE_W_ADDR >> 2] == TILE_W
    assert cpu.mode == MODE_USER
    table.close()


def test_b1b_untiled_spawn_stays_inert_super():
    """No tile arg -> exactly the legacy item-26 posture: TILE_H == 0 (the
    tile predicate is inert) and MODE_SUPER (no box check)."""
    table = GlyphProcessTable()
    pid = table.spawn(_exit_prog(0), name="legacy")
    cpu = table.tasks[pid]["cpu"]
    assert cpu.memory[TILE_H_ADDR >> 2] == 0
    assert cpu.mode == MODE_SUPER
    table.close()


# ── B2: in-tile store lands ──────────────────────────────────────────────
def test_b2_in_tile_store_lands():
    table = GlyphProcessTable()
    pid = table.spawn(
        _ram_writer_prog(0x0BADC0DE, addr=IN_TILE_WORD),
        name="in_tile", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    assert table.wait(pid) == EXIT_OK
    cpu = table.tasks[pid]["cpu"]
    assert cpu.memory[IN_TILE_WORD] == 0x0BADC0DE
    assert cpu.faulted is False
    table.close()


# ── B3: out-of-tile store traps, store does not land ────────────────────
def test_b3_out_of_tile_store_traps():
    """Tile WITHOUT an explicit reaper_pc: the table still arms the default
    reaper (a fence without a catcher trap-straight-to-(0,0), restarts the
    program in SUPER, and the re-executed store LANDS — see spawn() docstring).
    With the catcher armed the store never lands and the task parks on the
    trampoline, reaped."""
    table = GlyphProcessTable()
    pid = table.spawn(
        _ram_writer_prog(0xDEADBEEF, addr=OUT_TILE_WORD),
        name="escaping", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    status = table.wait(pid)
    cpu = table.tasks[pid]["cpu"]
    # The offending store NEVER landed.
    assert cpu.memory[OUT_TILE_WORD] == 0, "out-of-tile store landed — containment breached"
    # The engine raised the E-K1 fault (not a silent halt), with evidence.
    assert cpu.faulted is True
    assert cpu.memory[FAULT_ADDR_ADDR >> 2] == OUT_TILE_WORD * 4
    assert cpu.memory[FAULT_PC_ADDR >> 2] == (0 << 16) | 2
    # Parked on the auto-armed default reaper, halted.
    assert cpu.pc == (0, DEFAULT_REAPER_ROW)
    assert cpu.running is False
    # And the table reaper mapped it to the fault exit code.
    assert status == EXIT_FAULT
    assert table.state(pid) == "exited"
    table.close()


# ── B4: reaper vector + neighbor isolation ───────────────────────────────
def test_b4_reaper_vector_and_neighbor_survives():
    table = GlyphProcessTable()
    bad_pid = table.spawn(
        _ram_writer_prog(0xFEEDFACE, addr=400),  # 400 is outside every tile
        name="offender", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W),
        reaper_pc=(DEFAULT_REAPER_ROW << 16))
    good_pid = table.spawn(
        _ram_writer_prog(0x12345678, addr=IN_TILE_WORD),
        name="neighbor", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W),
        reaper_pc=(DEFAULT_REAPER_ROW << 16))
    statuses = table.wait_all()
    bad_cpu = table.tasks[bad_pid]["cpu"]
    # Offender: faulted, trapped to the reaper row in SUPER, evidence words set.
    assert statuses[bad_pid] == EXIT_FAULT
    assert bad_cpu.faulted is True
    assert bad_cpu.mode == MODE_SUPER
    assert bad_cpu.memory[FAULT_ADDR_ADDR >> 2] == 400 * 4
    assert bad_cpu.memory[FAULT_PC_ADDR >> 2] == (0 << 16) | 2
    # Parked on the reaper trampoline (row 30, col 0), halted — no re-execution.
    assert bad_cpu.pc == (0, DEFAULT_REAPER_ROW)
    assert bad_cpu.running is False
    assert bad_cpu.halt_reason is None  # clean HALT on the trampoline
    # The offending ST NEVER landed — containment held through the reaper path.
    assert bad_cpu.memory[400] == 0
    # The task executed against the WRAPPED image (the reaper row exists in
    # the table's copy; the spawner's original image is not mutated).
    assert table.tasks[bad_pid]["image"].shape[0] >= DEFAULT_REAPER_ROW + 1
    # Neighbor: clean exit, its own tile write landed.
    assert statuses[good_pid] == EXIT_OK
    assert table.tasks[good_pid]["cpu"].memory[IN_TILE_WORD] == 0x12345678
    table.close()


# ── P5: boundary semantics + zero-extent refusal ─────────────────────────
def test_p5_tile_boundary_semantics():
    # Last word INSIDE the tile: lands.
    last_in_tile = (TILE_ROW + TILE_H - 1) * W_MEM + TILE_COL + TILE_W - 1  # 195
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=8)
    cpu.memory = [0] * 16384
    arm_tile(cpu, (TILE_ROW, TILE_COL, TILE_H, TILE_W))
    # Raw-engine legs must arm their own catcher (the table does this at
    # spawn): vector to the program's own HALT would re-execute in SUPER,
    # so use the trampoline-row shape with a wrapped image.
    cpu.memory[KFAULT_PC_ADDR >> 2] = DEFAULT_REAPER_ROW << 16
    img = wrap_with_reaper(_ram_writer_prog(0x0F0F0F0F, addr=last_in_tile),
                           DEFAULT_REAPER_ROW, om)
    cpu.run(img, max_instructions=50)
    assert cpu.memory[last_in_tile] == 0x0F0F0F0F
    assert cpu.faulted is False

    # First word OUTSIDE (same row band, col == TILE_W): faults, no land.
    cpu2 = GlyphCPUv2(om, cols_instrs=8)
    cpu2.memory = [0] * 16384
    arm_tile(cpu2, (TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu2.memory[KFAULT_PC_ADDR >> 2] = DEFAULT_REAPER_ROW << 16
    img2 = wrap_with_reaper(_ram_writer_prog(0x11111111, addr=OUT_TILE_WORD),
                            DEFAULT_REAPER_ROW, om)
    cpu2.run(img2, max_instructions=50)
    assert cpu2.memory[OUT_TILE_WORD] == 0
    assert cpu2.faulted is True
    om.close()


def test_p5b_zero_extent_tile_refused():
    """A zero-extent tile is the engine's 'inert' encoding; refusing it at
    spawn means no caller can ask for USER mode without a real fence."""
    with pytest.raises(ContainmentError):
        arm_tile(GlyphCPUv2.__new__(GlyphCPUv2), (0, 0, 0, 4))
    table = GlyphProcessTable()
    with pytest.raises(GlyphProcessError):
        table.spawn(_exit_prog(0), tile=(TILE_ROW, TILE_COL, 0, TILE_W))
    table.close()


# ── R1: migration — item-26 contract unchanged on this tree ─────────────
def test_r1_item26_ram_writer_contract_unchanged():
    table = GlyphProcessTable()
    pid_a = table.spawn(_ram_writer_prog(0x5A5A5A), name="writerA")
    pid_b = table.spawn(_ram_writer_prog(0x000001), name="writerB")
    table.wait_all()
    a = table.tasks[pid_a]["cpu"]
    b = table.tasks[pid_b]["cpu"]
    assert a.memory[DATA_ADDR] == 0x5A5A5A
    assert b.memory[DATA_ADDR] == 0x000001
    # EXIT-status contract still exact.
    pid_x = table.spawn(_exit_prog(7), name="exiter")
    assert table.wait(pid_x) == 7
    table.close()


# ── R2: the item-26 gate re-runs GREEN in this tree ─────────────────────
def test_r2_item26_gate_rerun():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_item26_process.py",
         "-q", "-p", "no:randomly"],
        cwd=repo, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"item-26 gate RED in item-29 tree:\n{r.stdout[-2000:]}\n{r.stderr[-500:]}"
    assert " passed" in r.stdout


# ── N1: engine-byte guard (non-vacuity for the whole approach) ──────────
def test_n1_engine_byte_unchanged():
    """tools/glyph_isa_v2.py must be byte-identical to HEAD: item-29 arms
    an EXISTING engine contract from the host side. If the engine drifted,
    every containment premise in this gate is unverified."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    blob = subprocess.run(["git", "rev-parse", f"HEAD:tools/glyph_isa_v2.py"],
                          cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    on_disk = subprocess.run(["git", "hash-object", "tools/glyph_isa_v2.py"],
                             cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    assert blob == on_disk, (
        f"engine drift: HEAD blob {blob} != on-disk {on_disk} — "
        "item-29 claims no-engine-change; investigate before trusting this gate")
