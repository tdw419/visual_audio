#!/usr/bin/env python3
"""BK-40 gate — syscall-layer fence guard (step 3 of the sequenced fence
commit; row: systems/GLYPH_BACKLOG.md BK-40).

DEFECT (measured at HEAD 802b6ac8, probe .builder_queue/probe_syscall_fence
_af3e.py, md5 cee48c7b5a5e328693361564b7b761f4): the syscall DATA handlers
0x02 READ / 0x04 FILE_READ / 0x13 FILE_LIST write any RAM word, and 0x11
STORE_CODE writes any image pixel, from a tiled USER task — clean exit, no
trap — while plain ST to the same word traps E-K1.

POSTURE (decided at landing, row option 1 — the KSYS-arm alternative was
already measured REJECTED by BK-41): per-op dest-window consult at the
SYSCALL dispatch site. BEFORE the handler runs, the engine derives the
handler's dest window from the register file (r1=addr, r2=len conventions
per handler, read at consult time) and refuses the WHOLE syscall via the
landed E-K1 tail (_stack_fence_fault contract: fault_addr = word<<2,
fault_pc packed, mode->SUPER, KFAULT_PC vector, kf==0 stop) when any byte
of the window falls out of the fence term _addr_in_box (boxes + GO-2
tile). Handler never runs on refusal: nothing lands, no partial copy.
Covered handlers: 0x02 READ, 0x04 FILE_READ (+VFS arm), 0x13 FILE_LIST
(+VFS arm), 0x11 STORE_CODE (image-plane class, judged word-wise).
USER + _tile_confinement + _iso_enabled only — the same term set as every
landed fence consult; SUPER handlers (E-K2 dispatch) and unfenced tasks
are untouched. The BK-42/43 path-decoder consults are separate rows, NOT
this gate.

Legs:
  L1  0x02 READ dest out-of-tile -> fault, bytes dropped, rc EXIT_FAULT.
  L2  0x04 FILE_READ dest out-of-tile -> fault, bytes dropped.
  L3  0x13 FILE_LIST dest out-of-tile -> fault, bytes dropped.
  L4  0x11 STORE_CODE dest out-of-tile -> fault, pixel unchanged.
  L5  in-tile controls for all four handlers stay green (the fence must
      not brick lawful data handlers).
  L6  ST-out-of-tile trap control (fault_addr = dest*4, E-K1 baseline).
  L7  non-vacuity: the dest consult neutered in a TEMP-COPY module ->
      L1's shape returns (bytes land clean); real tree md5-pinned.
  L8  family: BK-41 + BK-39 + item-29 gates green on this tree (never
      weaken a live guard).

RED-first at landing time: run against the UNFIXED tree (engine fix
stashed) — L1..L4 fail with the measured pre-fix shapes (clean exit,
bytes/pixel land); L5..L8 pass (harness live). Fix applied -> 8/8.
"""
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, INPUT_DATA_ADDR, INPUT_LEN_ADDR,
    OpcodeMapV2, W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 168: first word outside
#   the tile (rows 5-12 x cols 0-7). The BK-40 probe's geometry disclosure:
#   160+64=224 is row 7 col 0 = INSIDE; do not "simplify" this back.
FR_IN_DEST = IN_TILE_WORD + 2                      # 162: in-tile ctl dest
#   (176 is OUT of the tile — (5,16), cols 0-7 only. First draft labeled
#   176 "in-tile", which made L5's FILE_READ control trap on the real
#   fence and would have hidden a real regression as a "passing" RED.)
FIXTURE = "/tmp/bk"
FIXTURE_BYTES = b"KFENCE"
CANARY_BYTE = 0x4B                                  # 'K'


def _build(lines):
    return GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)


def _spawn(img, neuter=False):
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk40", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    if neuter:
        # Non-vacuity instrument: the dest consult admits everything ->
        # the syscall fence must go silent and the pre-fix behavior must
        # reappear. Same instrument style as BK-39 L6 / BK-41 L5.
        cpu._bk40_dest_fault = lambda dest, length, kind: None
    task_img = table.tasks[pid]["image"]
    rc = table.wait(pid)
    return table, cpu, task_img, rc


def _stage_path(path_bytes, sysnum, dest, max_bytes=8):
    """Stage an in-tile NUL-terminated path at word 160 (PARALLEL_ST mirror
    hits pixel 160 = instruction 40, past a <=30-instruction program), then
    issue the syscall. r1=path_addr, r2=dest, r3=max_bytes (declared dest
    window — the consult judges it; keep it tight on in-tile controls).

    GATE-DRAFT DEFECT, caught by L5's control failing (receipted): the first
    draft staged a 22-byte path, words 160..181 — word 168 is OUT of the
    tile (rows 5-12 x cols 0-7), so the landed BK-39 fence trapped the
    STAGING PARALLEL_ST itself and L2 passed VACUOUSLY (staging fault, not
    the syscall verdict). Fix: short path (7 bytes + terminator, words
    160..167, all in-tile) — the probe's original staging shape."""
    out = []
    for i, b in enumerate(path_bytes):
        out += ["LDI r5 %d" % (160 + i), "LDI r6 %d" % b,
                "PARALLEL_ST r5 r6 1"]
    out += ["LDI r5 %d" % (160 + len(path_bytes)), "LDI r6 0",
            "PARALLEL_ST r5 r6 1"]                      # terminator, in-tile
    out += [
        "LDI r1 160",
        "LDI r2 %d" % dest,
        "LDI r3 %d" % max_bytes,
        "SYSCALL r10 %d" % sysnum,
        "HALT",
    ]
    return out


def _seed_ring(cpu):
    cpu.memory[INPUT_DATA_ADDR >> 2] = ord("K")
    cpu.memory[(INPUT_DATA_ADDR >> 2) + 1] = ord("F")
    cpu.memory[INPUT_LEN_ADDR >> 2] = 2


def _word_hex(w):
    return bytes([w & 0xFF, (w >> 8) & 0xFF]).hex()


def _run_case(prog, seed=None, neuter=False):
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk40", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    if neuter:
        cpu._bk40_dest_fault = lambda dest, length, kind: None
    _seed_ring(cpu)
    for addr, val in (seed or {}).items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    pre_pix = tuple(int(v) for v in table.tasks[pid]["image"][
        OUT_TILE_WORD // W_MEM, OUT_TILE_WORD % W_MEM])
    rc = table.wait(pid)
    post_pix = tuple(int(v) for v in table.tasks[pid]["image"][
        OUT_TILE_WORD // W_MEM, OUT_TILE_WORD % W_MEM])
    return {
        "rc": rc,
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "reason": (cpu.fault_reason or ""),
        "out_word": int(cpu.memory[OUT_TILE_WORD]),
        "out_hex": _word_hex(int(cpu.memory[OUT_TILE_WORD])),
        "in_hex": _word_hex(int(cpu.memory[IN_TILE_WORD])),
        "out_pix_changed": post_pix != pre_pix,
        "mode_super": int(cpu.mode) == 0,
    }


# ── L1: 0x02 READ dest out-of-tile -> refused ───────────────────────────
def test_l1_read_dest_out_of_tile_traps():
    """RED today: clean exit, 'K' lands at 168."""
    prog = ["LDI r1 %d" % OUT_TILE_WORD, "LDI r2 2", "SYSCALL r10 2", "HALT"]
    r = _run_case(prog, seed={OUT_TILE_WORD: 0})
    assert r["rc"] == EXIT_FAULT, r
    assert r["faulted"], r
    assert r["fault_addr"] == OUT_TILE_WORD * 4, r
    assert "syscall_dest_fence" in r["reason"], r
    assert r["out_hex"] == "0000", r          # nothing landed
    assert r["mode_super"], r                 # E-K1 tail: mode -> SUPER


# ── L2: 0x04 FILE_READ dest out-of-tile -> refused ──────────────────────
def test_l2_file_read_dest_out_of_tile_traps():
    """RED today: clean exit, 'KF' lands at 168."""
    with open(FIXTURE, "wb") as f:
        f.write(FIXTURE_BYTES)
    prog = _stage_path(FIXTURE.encode(), 4, OUT_TILE_WORD)
    r = _run_case(prog, seed={OUT_TILE_WORD: 0})
    assert r["rc"] == EXIT_FAULT, r
    assert r["faulted"], r
    assert r["fault_addr"] == OUT_TILE_WORD * 4, r
    assert "syscall_dest_fence" in r["reason"], r
    assert r["out_hex"] == "0000", r


# ── L3: 0x13 FILE_LIST dest out-of-tile -> refused ──────────────────────
def test_l3_file_list_dest_out_of_tile_traps():
    """RED today: clean exit, listing bytes land at 168. GLYPH_FS_ALLOW
    scoped to /tmp so the allowlist check passes and the DEST consult is
    the site under test (never weaken a live guard: the allowlist itself
    stays live — a denied listing would zero-fault differently)."""
    env = dict(os.environ, GLYPH_FS_ALLOW="/tmp")
    prog = _stage_path(b"/tmp", 0x13, OUT_TILE_WORD)
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk40_l3", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    _seed_ring(cpu)
    cpu.memory[OUT_TILE_WORD] = 0
    pre_pix = tuple(int(v) for v in table.tasks[pid]["image"][
        OUT_TILE_WORD // W_MEM, OUT_TILE_WORD % W_MEM])
    rc = table.wait(pid)
    post_pix = tuple(int(v) for v in table.tasks[pid]["image"][
        OUT_TILE_WORD // W_MEM, OUT_TILE_WORD % W_MEM])
    assert rc == EXIT_FAULT
    assert cpu.faulted
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4
    assert int(cpu.memory[OUT_TILE_WORD]) == 0
    assert post_pix == pre_pix
    # the listing handler must NOT have run: host dir listing would have
    # written '.' (0x2E) first
    del env


# ── L4: 0x11 STORE_CODE dest out-of-tile -> refused ─────────────────────
def test_l4_store_code_dest_out_of_tile_traps():
    """RED today: clean exit, image pixel at word 168 changes."""
    prog = ["LDI r1 %d" % OUT_TILE_WORD, "LDI r2 200", "LDI r3 1",
            "SYSCALL r10 17", "HALT"]
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk40_l4", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    task_img = table.tasks[pid]["image"]
    task_img[200 // W_MEM, 200 % W_MEM] = (0x41, 0x42, 0x43)
    _seed_ring(cpu)
    rc = table.wait(pid)
    post = tuple(int(v) for v in task_img[OUT_TILE_WORD // W_MEM,
                                          OUT_TILE_WORD % W_MEM])
    assert rc == EXIT_FAULT, (rc, post)
    assert cpu.faulted
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4
    assert post == (0, 0, 0), post            # the copy never fired


# ── L5: in-tile controls stay green for all four handlers ───────────────
def test_l5_in_tile_controls_land():
    # 0x02 READ in-tile
    r = _run_case(["LDI r1 %d" % IN_TILE_WORD, "LDI r2 2",
                   "SYSCALL r10 2", "HALT"], seed={IN_TILE_WORD: 0})
    assert r["rc"] == EXIT_OK and r["in_hex"] == "4b00", r
    # 0x04 FILE_READ in-tile. POSTURE (declared-window, documented): the
    # consult judges the DECLARED count (r3), not the actual bytes — the
    # real length is host-data-dependent and unknowable before the
    # handler runs (judging actual = partial-copy race, the thing the
    # refusal forbids). A tile-confined task declares max <= tile space;
    # r3=6 here matches the fixture exactly. Over-confinement bites only
    # oversized declared windows, which IS the attack shape (a task may
    # not declare a write window broader than its confinement).
    with open(FIXTURE, "wb") as f:
        f.write(FIXTURE_BYTES)
    prog = _stage_path(FIXTURE.encode(), 4, FR_IN_DEST, max_bytes=6)
    r = _run_case(prog, seed={FR_IN_DEST: 0})
    assert r["rc"] == EXIT_OK, r
    assert r["faulted"] is False, r
    assert r["fault_addr"] == 0, r
    # 0x11 STORE_CODE in-tile
    prog = ["LDI r1 %d" % FR_IN_DEST, "LDI r2 200", "LDI r3 1",
            "SYSCALL r10 17", "HALT"]
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk40_l5sc", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    task_img = table.tasks[pid]["image"]
    task_img[200 // W_MEM, 200 % W_MEM] = (0x41, 0x42, 0x43)
    rc = table.wait(pid)
    post = tuple(int(v) for v in task_img[FR_IN_DEST // W_MEM,
                                          FR_IN_DEST % W_MEM])
    assert rc == EXIT_OK and post == (0x41, 0x42, 0x43), (rc, post)


# ── L6: ST-out-of-tile trap control (E-K1 baseline intact) ──────────────
def test_l6_st_out_of_tile_control():
    prog = ["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 4660", "ST r2 r3", "HALT"]
    r = _run_case(prog, seed={OUT_TILE_WORD: 0})
    assert r["rc"] == EXIT_FAULT and r["fault_addr"] == OUT_TILE_WORD * 4, r


# ── L7: non-vacuity — neuter the consult, pre-fix shape returns ─────────
def test_l7_non_vacuity():
    """The consult neutered (TEMP-COPY-free instrument: instance attribute
    shadowing the method, engine file untouched on disk) -> L1's exact
    program must land 'K' at 168 clean. Real-tree md5 pinned before/after
    so the neuter provably did not edit the engine."""
    engine = REPO / "tools" / "glyph_isa_v2.py"
    md5_before = hashlib.md5(engine.read_bytes()).hexdigest()
    prog = ["LDI r1 %d" % OUT_TILE_WORD, "LDI r2 2", "SYSCALL r10 2", "HALT"]
    r = _run_case(prog, seed={OUT_TILE_WORD: 0}, neuter=True)
    md5_after = hashlib.md5(engine.read_bytes()).hexdigest()
    assert md5_before == md5_after == _ENGINE_MD5, (md5_before, md5_after)
    assert r["rc"] == EXIT_OK, r
    assert r["out_hex"] == "4b00", r          # the pre-fix shape reproduced
    assert not r["faulted"], r


_ENGINE_MD5 = hashlib.md5(
    (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()


# ── L8: family — BK-41 + BK-39 + item-29 gates green on this tree ───────
def test_l8_family():
    for gate in ("tests/test_bk41_ksys_fence.py",
                 "tests/test_bk39_write_fence.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert p.returncode == 0, (gate, p.stdout[-2000:])
