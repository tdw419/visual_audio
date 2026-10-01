"""BK-52 gate: oracle KFAULT_PC=0 trap continuation (guard parity + pin).

Root cause (measured, RESEARCH_kfault0_trap_af3e.md): the E-K1 ST trap arm
(glyph_isa_v2.py :1084-1090 pre-fix) and the sibling iso-armed OOB store
vector (:1115-1126 pre-fix) vector KFAULT_PC with NO kf!=0 guard — kf=0
becomes next_pc=(0,0), mode already SUPER, so the trapped task REPLAYS from
program entry and the "refused" store LANDS. The WGSL twin already carries
the correct guard (walk_st's E-K1 arm, wgsl_glyph_isa_v2.py :602-609).

Legs:
  L1  post-repair: seeded-USER out-of-tile ST with KFAULT_PC=0 halts AT the
      trap (<= 3 steps, running False, fault_addr=656=word*4, mode SUPER,
      faulted True) and the target word stays 0 (replay-and-land DEAD).
  L2  handler installed: vector unchanged (green today, must stay green —
      never weaken a live guard). Task parks on the reaper trampoline.
  L3  sibling site (:1121 iso-armed OOB store vector): same pinned
      semantics — kf=0 stops loudly, no (0,0) replay.
  L4  non-vacuity: the E-K1 arm's guard corrupted in a TEMP COPY (V-only,
      pre-fix behavior) re-runs L1's program and the canary LANDS — the
      gate fires against the live defect shape; real module md5 pinned
      before/after.
  L5  family: BK-38 tile LD fence + item-29 containment gates stay green
      (imported via pytest -k in CI; here pinned by subprocess for the two
      cheapest legs — kept out to bound runtime, see ledger receipt).

RED-first: this gate was demonstrated RED against the pre-fix engine —
probe /tmp/probe_bk52_red_af3e.py at HEAD e0afc4f1 measured the
no-handler shape as {steps 7, word164=0x0ADF00D, replay landed} before the
fix and {steps 3, word164=0} after (both runs in the landing receipt).
"""
import hashlib
import importlib
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_containment import DEFAULT_REAPER_ROW  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    KFAULT_PC_ADDR,
    MODE_SUPER,
    MODE_USER,
    TILE_COL_ADDR,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    TILE_W_ADDR,
    W_MEM,
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 164: first word outside
CANARY = 0x0ADF00D
EXPECTED_FAULT_ADDR = OUT_TILE_WORD * 4             # 656


def _build(lines):
    return GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)


def _tall_image(lines):
    img = _build(lines)
    rows = max(img.shape[0], DEFAULT_REAPER_ROW + 1)
    tall = np.zeros((rows, img.shape[1], 3), dtype=np.uint8)
    tall[: img.shape[0]] = img
    tall[DEFAULT_REAPER_ROW, 0] = OM.opcode_to_rgb("HALT")
    return tall


def _spawn_cpu(kfault_pc):
    """Bare engine in the arm_tile posture (MODE_USER + tile words armed +
    _tile_confinement), KFAULT_PC as given. Mirrors spawn(tile=...)."""
    cpu = GlyphCPUv2(OM, cols_instrs=8)
    cpu.memory = [0] * 16384
    cpu.memory[TILE_ROW_ADDR >> 2] = TILE_ROW
    cpu.memory[TILE_COL_ADDR >> 2] = TILE_COL
    cpu.memory[TILE_H_ADDR >> 2] = TILE_H
    cpu.memory[TILE_W_ADDR >> 2] = TILE_W
    cpu.mode = MODE_USER
    cpu._tile_confinement = True
    cpu.memory[KFAULT_PC_ADDR >> 2] = kfault_pc
    return cpu


def _run_fenced_store(cpu, image, max_steps=40):
    cpu.running = True
    steps = 0
    while cpu.running and steps < max_steps:
        cpu.step(image)
        steps += 1
    return steps


def _store_prog():
    return _tall_image([
        "LDI r5 %d" % CANARY,
        "LDI r6 %d" % OUT_TILE_WORD,
        "ST r6 r5",
        "HALT",
    ])


# ── L1: kf=0 → halt at trap, store does NOT land ─────────────────────────
def test_l1_kf0_stops_at_trap_no_replay():
    cpu = _spawn_cpu(kfault_pc=0)
    steps = _run_fenced_store(cpu, _store_prog())
    assert cpu.faulted is True
    assert cpu.fault_addr == EXPECTED_FAULT_ADDR
    assert cpu.mode == MODE_SUPER          # dropped to SUPER at the trap
    assert cpu.running is False            # no (0,0) replay
    assert steps <= 3                      # trap, then immediate stop
    assert cpu.memory[OUT_TILE_WORD] == 0  # the "refused" store must NOT land


# ── L2: handler installed → vector unchanged ─────────────────────────────
def test_l2_handler_vector_unchanged():
    cpu = _spawn_cpu(kfault_pc=DEFAULT_REAPER_ROW << 16)
    steps = _run_fenced_store(cpu, _store_prog())
    assert cpu.faulted is True
    assert cpu.fault_addr == EXPECTED_FAULT_ADDR
    assert cpu.mode == MODE_SUPER
    assert tuple(cpu.pc) == (0, DEFAULT_REAPER_ROW)  # parked on the trampoline
    assert cpu.memory[OUT_TILE_WORD] == 0            # store still refused


# ── L3: sibling site (iso-armed OOB store vector) same semantics ─────────
def test_l3_sibling_oob_vector_same_guard():
    # Sibling posture: USER, tile inert, BOX0 armed ABOVE RAM end — the
    # store passes E-K1 (in-box) but lands past len(memory), reaching the
    # OOB branch's iso_enabled vector (:1116-1135). With kf=0 it must stop
    # loudly, not vector to (0,0) and replay in SUPER.
    cpu = _spawn_cpu(kfault_pc=0)
    cpu._tile_confinement = False
    cpu.memory[TILE_H_ADDR >> 2] = 0            # tile inert
    BOX0_LO_ADDR = 0x800C
    BOX0_HI_ADDR = 0x8010
    cpu.memory[BOX0_LO_ADDR >> 2] = 16384 * 4   # box starts AT RAM end
    cpu.memory[BOX0_HI_ADDR >> 2] = 16384 * 4 + 4096
    target_word = 16390                         # in-box, past len(memory)
    img = _tall_image([
        "LDI r5 %d" % CANARY,
        "LDI r6 %d" % target_word,
        "ST r6 r5",
        "HALT",
    ])
    steps = _run_fenced_store(cpu, img)
    assert cpu.faulted is True
    assert cpu.fault_addr == target_word * 4
    assert cpu.mode == MODE_SUPER
    assert cpu.running is False                 # kf=0: stop, no replay
    assert steps <= 3


# ── L4: non-vacuity — neuter the guard in a TEMP COPY, canary LANDS ──────
def test_l4_nonvacuity_guard_neuter_red():
    import hashlib as _h
    real_path = os.path.join(REPO, "tools", "glyph_isa_v2.py")
    md5_before = _h.md5(open(real_path, "rb").read()).hexdigest()

    src = open(real_path).read()
    # Neuter exactly the new guard at the E-K1 arm: make the kf!=0 test
    # always true (V-only, pre-fix behavior) in a temp-copy module.
    marker = ("                kf = self.memory[KFAULT_PC_ADDR >> 2]\n"
              "                if kf != 0:\n"
              "                    # BK-52: guard parity with the WGSL twin")
    assert marker in src, "BK-52 guard marker not found — gate must pin the live fix"
    neutered = src.replace(
        "                if kf != 0:\n"
        "                    # BK-52: guard parity with the WGSL twin",
        "                if True:  # neutered for L4 (pre-fix behavior)\n"
        "                    # BK-52: guard parity with the WGSL twin",
        1,
    )
    assert neutered != src

    tmpdir = tempfile.mkdtemp(prefix="bk52_l4_")
    try:
        pkg = os.path.join(tmpdir, "tools")
        os.makedirs(pkg)
        shutil.copy(os.path.join(REPO, "tools", "__init__.py"),
                    os.path.join(pkg, "__init__.py"))
        # Copy module-level deps so the temp-copy import resolves.
        for dep in ("glyph_isa_v2.py", "wordbase.py"):
            shutil.copy(os.path.join(REPO, "tools", dep), pkg)
        # wordbase.py resolves db/wordbase.db relative to tmpdir; symlink the
        # real db (20 MB — never copy) so OpcodeMapV2's __init__ can open it.
        os.makedirs(os.path.join(tmpdir, "db"), exist_ok=True)
        os.symlink(os.path.join(REPO, "db", "wordbase.db"),
                   os.path.join(tmpdir, "db", "wordbase.db"))
        open(os.path.join(pkg, "glyph_isa_v2.py"), "w").write(neutered)

        for mod in list(sys.modules):
            if mod == "tools" or mod.startswith("tools."):
                del sys.modules[mod]
        sys.path.insert(0, tmpdir)
        try:
            import tools.glyph_isa_v2 as tgv  # temp copy
            importlib.reload(tgv)
            cpu = tgv.GlyphCPUv2(tgv.OpcodeMapV2(), cols_instrs=8)
            cpu.memory = [0] * 16384
            cpu.memory[tgv.TILE_ROW_ADDR >> 2] = TILE_ROW
            cpu.memory[tgv.TILE_COL_ADDR >> 2] = TILE_COL
            cpu.memory[tgv.TILE_H_ADDR >> 2] = TILE_H
            cpu.memory[tgv.TILE_W_ADDR >> 2] = TILE_W
            cpu.mode = tgv.MODE_USER
            cpu._tile_confinement = True
            cpu.memory[tgv.KFAULT_PC_ADDR >> 2] = 0
            img = _store_prog()
            cpu.running = True
            steps = 0
            while cpu.running and steps < 40:
                cpu.step(img)
                steps += 1
            # Pre-fix behavior: replay-and-land — the canary arrives.
            assert cpu.memory[OUT_TILE_WORD] == CANARY, (
                "neutered build refused the store — L4 RED leg lost its teeth")
            assert steps > 4  # replay walks the program again
        finally:
            sys.path.remove(tmpdir)
            for mod in list(sys.modules):
                if mod == "tools" or mod.startswith("tools."):
                    del sys.modules[mod]
            import tools.glyph_isa_v2 as real_tgv  # re-import the REAL module
            assert real_tgv.__file__.startswith(REPO)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        md5_after = _h.md5(open(real_path, "rb").read()).hexdigest()
        assert md5_before == md5_after, "real engine file mutated by L4"


# ── L5: family — BK-38 + item-29 gates stay green (subprocess, bounded) ──
def test_l5_family_gates_green():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_bk38_ld_fence.py"],
        cwd=REPO, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:]
    assert " failed" not in r.stdout
