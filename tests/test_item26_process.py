"""item-26 gate: spatial process model (spawn primitive + multi-task coordination).

Legs:
  P1  spawn isolation — two tasks, fresh engines each: task A's RAM write
      is invisible to task B (SE021 isolation delta, in-process).
  P2  spawn + wait exit-status contract: explicit SYSCALL 0x05 EXIT r1=7
      -> wait() == 7; clean HALT (no EXIT) -> 0 (child-runner rc contract);
      faulted engine -> 1.
  P3  multi-task coordination — wait_all over 3 concurrent spawned tasks;
      each produces its own PRT stream byte-exact; statuses correct.
  P4  shared-VFS coordination — two tasks, ONE GlyphVfs (item-25's landed
      arms, unmodified): task A 0x03-writes through the VFS, task B 0x04-
      reads the SAME name and gets A's bytes byte-exact; wait ordering
      enforced by the table (A waited before B runs).
  P5  wait_any returns the first ready task in pid order with a valid
      (pid, status) pair; state() transitions ready -> exited.
  R1  MIGRATION: engine default — a bare GlyphCPUv2 (no table) still
      runs a 0x05 EXIT program exactly as before (hook is keyed on the
      table's subclass, base-class behavior byte-unchanged).
  R2  MIGRATION: item-25 VFS gate re-run GREEN in this tree via
      subprocess (the process table touches no VFS code path).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (statuses, bytes, states, RAM words).
"""
import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessError, GlyphProcessTable  # noqa: E402
from tools.glyph_vfs import GlyphVfs  # noqa: E402

DATA_ADDR = 400   # above the program window (width 8 -> ~40 instrs used)
OUT_ADDR = 800


def _prog(lines):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def _ram_writer_prog(value: int) -> np.ndarray:
    """ST r6, r5 form: memory[r6]=r5, then HALT — the task-isolation probe."""
    return _prog([
        f"LDI r5 {value}",
        f"LDI r6 {DATA_ADDR}",
        "ST r6 r5",
        "HALT",
    ])


def _exit_prog(status: int) -> np.ndarray:
    return _prog([
        f"LDI r1 {status}",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _prt_prog(text: bytes) -> np.ndarray:
    prog = []
    for b in text:
        prog += [f"LDI r5 {b}", "PRT r5"]
    prog += ["HALT"]
    return _prog(prog)


# ── P1: spawn isolation ──────────────────────────────────────────────────
def test_p1_spawn_isolation_fresh_engines():
    table = GlyphProcessTable()
    pid_a = table.spawn(_ram_writer_prog(0x5A5A5A), name="writerA")
    pid_b = table.spawn(_ram_writer_prog(0x000001), name="writerB")
    assert pid_a != pid_b
    table.wait_all()
    a = table.tasks[pid_a]["cpu"]
    b = table.tasks[pid_b]["cpu"]
    assert a is not b
    assert a.memory[DATA_ADDR] == 0x5A5A5A
    # B never saw A's write: B's own program stored 1 there, and B ran in
    # its own RAM — the value B's memory holds is B's own, not A's.
    assert b.memory[DATA_ADDR] == 0x000001
    # B's RAM word is not A's post-run word even at unrelated addresses:
    # A's register file holds 0x5A5A5A in r5; B's r5 is B's own value.
    assert a.registers[5] == 0x5A5A5A
    assert b.registers[5] == 0x000001
    table.close()


# ── P2: exit-status contract ─────────────────────────────────────────────
def test_p2_exit_status_contract():
    table = GlyphProcessTable()
    assert table.spawn(_exit_prog(7), name="exiter") >= 1
    pid_halt = table.spawn(_prt_prog(b"done"), name="halter")  # clean HALT, no EXIT
    assert table.wait(1) == 7
    assert table.wait(pid_halt) == EXIT_OK
    # opcode-None is a clean silent halt (landed halt_reason contract,
    # glyph_isa_v2.py:766-769 — running=False, faulted stays False), so
    # rc 0; the genuinely-FAULTED engine is P2b's leg.
    bad = _prt_prog(b"x").copy()
    bad[0, 0] = (250, 250, 250)  # not a known opcode color
    pid_bad = table.spawn(bad, name="badop")
    assert table.wait(pid_bad) == EXIT_OK
    assert table.state(pid_bad) == "exited"
    table.close()


def test_p2b_faulted_engine_rc1():
    """A genuinely faulted engine maps to rc 1 (child-runner contract)."""
    table = GlyphProcessTable()
    # SpatialMisalignmentFault class: JNZ/JMP are aligned by encoding, so
    # produce a fault the engine ACTUALLY raises on run(): a box check is
    # SUPER-mode inert; the reachable fault without a kernel is the
    # alignment check on a crafted PC. Drive it directly: spawn normally,
    # then re-point the engine's pc to an unaligned x before wait.
    pid = table.spawn(_prt_prog(b"ok"), name="misaligned")
    cpu = table.tasks[pid]["cpu"]
    cpu.pc = (2, 0)  # x not a multiple of INSTR_WIDTH=4
    with pytest.raises(Exception):
        table.wait(pid)
    assert table.tasks[pid]["exit_status"] == EXIT_FAULT
    table.close()


# ── P3: multi-task coordination ──────────────────────────────────────────
def test_p3_wait_all_three_tasks():
    table = GlyphProcessTable()
    texts = {1: b"ALPHA", 2: b"BETA", 3: b"GAMMA"}
    pids = {k: table.spawn(_prt_prog(v), name=f"t{k}") for k, v in texts.items()}
    statuses = table.wait_all()
    assert set(statuses) == set(pids)
    assert all(s == EXIT_OK for s in statuses.values())
    for k, txt in texts.items():
        assert table.output(pids[k]) == txt
        assert table.state(pids[k]) == "exited"
    table.close()


# ── P4: shared-VFS coordination (the spawn primitive's coordination leg) ──
def test_p4_shared_vfs_handoff_between_tasks(tmp_path):
    table = GlyphProcessTable()
    disk = str(tmp_path / "handoff.png")
    vfs = GlyphVfs.format(disk)

    payload = b"from-task-A-with-love"  # 21 bytes
    name = "handoff.txt"
    # Build the REAL write program: path at PATH_ADDR (RAM-seeded), data
    # at DATA_ADDR, len in r3.
    PATH_ADDR = 900
    assert len(name) + 1 + PATH_ADDR < 16384
    wprog = _prog([
        f"LDI r1 {PATH_ADDR}",
        f"LDI r2 {DATA_ADDR}",
        f"LDI r3 {len(payload)}",
        "SYSCALL r4 0x03",
        "HALT",
    ])
    rprog = _prog([
        f"LDI r1 {PATH_ADDR}",
        f"LDI r2 {OUT_ADDR}",
        f"LDI r3 {len(payload)}",
        "SYSCALL r4 0x04",
        "HALT",
    ])
    pid_a = table.spawn(wprog, name="taskA", vfs=vfs, vfs_shared=True)
    pid_b = table.spawn(rprog, name="taskB", vfs=vfs, vfs_shared=True)

    # Seed A's RAM (A's own engine — only A sees these bytes).
    a_cpu = table.tasks[pid_a]["cpu"]
    for i, ch in enumerate(name + "\0"):
        a_cpu.memory[PATH_ADDR + i] = ord(ch)
    for i, byte in enumerate(payload):
        a_cpu.memory[DATA_ADDR + i] = byte
    # Seed B's RAM identically for the PATH (same guest name) but NOT the
    # data window — B must receive A's bytes through the VFS.
    b_cpu = table.tasks[pid_b]["cpu"]
    for i, ch in enumerate(name + "\0"):
        b_cpu.memory[PATH_ADDR + i] = ord(ch)
    assert all(b_cpu.memory[OUT_ADDR + i] == 0 for i in range(len(payload)))

    # Ordering: A fully waited before B runs (cooperative table).
    assert table.wait(pid_a) == EXIT_OK
    assert table.wait(pid_b) == EXIT_OK

    # B's output window holds A's payload — through the shared VFS only.
    got = bytes(b_cpu.memory[OUT_ADDR:OUT_ADDR + len(payload)])
    assert got == payload, f"handoff mismatch: {got!r}"
    # Containment, REMEDY (System-1 item26 advisory, evidence b727fcb1):
    # the gate originally checked only tmp_path/name — but the engine's
    # no-VFS fallback (glyph_isa_v2.py:1509/1555) opens `path` relative to
    # the test process CWD, so a detached attach "passes" while the
    # payload escapes to CWD/handoff.txt (measured: mutation run landed
    # the exact 21-byte payload there). Assert the fallback's actual
    # escape path too — the check that makes the leg DISCRIMINATING.
    assert not (tmp_path / name).exists()
    assert not pathlib.Path(name).exists(), (
        f"VFS-2 containment breached: {name!r} landed via the host-FS "
        "fallback (no-VFS arm) — attach() did not take effect")
    table.close()


# ── P5: wait_any + state transitions ─────────────────────────────────────
def test_p5_wait_any_and_state():
    table = GlyphProcessTable()
    pid1 = table.spawn(_exit_prog(2), name="first")
    pid2 = table.spawn(_exit_prog(3), name="second")
    assert table.state(pid1) == "ready"
    got_pid, status = table.wait_any()
    assert got_pid == pid1 and status == 2
    assert table.state(pid1) == "exited"
    got_pid2, status2 = table.wait_any()
    assert got_pid2 == pid2 and status2 == 3
    # All exited: wait_any returns the FIRST exited pair (pid1), no re-run.
    p, s = table.wait_any()
    assert p == pid1 and s == 2
    with pytest.raises(GlyphProcessError):
        table.wait(9999)
    table.close()


# ── R1: migration — bare engine unchanged ────────────────────────────────
def test_r1_bare_engine_exit_unchanged():
    """No table involved: GlyphCPUv2 runs a 0x05 program exactly as landed."""
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(
        [f"LDI r1 9", "SYSCALL r0 0x05", "HALT"], width_instrs=8)
    cpu = GlyphCPUv2(om, cols_instrs=8)
    cpu.memory = [0] * 16384
    cpu.run(img)
    assert cpu.registers[0] == 9          # rc delivered to rd by the base handler
    assert cpu.running is False
    om.close()


# ── R2: migration — item-25 VFS gate re-run in this tree ─────────────────
def test_r2_item25_vfs_gate_still_green():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # The worktree's .venv is a bare python3.11 with no pytest; the main
    # tree's .venv carries it. Use whichever HAS pytest (the R2 leg is a
    # subprocess migration re-run, not a venv test).
    for cand in (os.path.join(repo, ".venv", "bin", "python"),
                 "/home/jericho/projects/zion/projects/visual_audio/.venv/bin/python",
                 sys.executable):
        probe = subprocess.run([cand, "-c", "import pytest"],
                               capture_output=True, timeout=60)
        if probe.returncode == 0:
            py = cand
            break
    else:
        pytest.skip("environment: no python with pytest for the migration subprocess")
    r = subprocess.run(
        [py, "-m", "pytest", "tests/test_item25_vfs.py", "-q", "--no-header", "-x"],
        cwd=repo, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"item-25 gate regressed in item-26 tree:\n{r.stdout[-2000:]}\n{r.stderr[-500:]}"
