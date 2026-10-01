#!/usr/bin/env python3
"""BK-41 gate — kernel-write-only BOX_MMIO CONFIG block (L1..L8).

DIRECTIVE: .builder_queue/DIRECTIVE_BK41_CONFIG_BLOCK.md (seat-lane
provisional, commit 49b4ba09; "you lead" 2026-09-30 12:41 CDT). Step 2 of
BK-39's resolution; companion to the landed BK-76 no-vector refusal.

POSTURE: every guest-reachable write arm refuses stores to the
guest-defeatable CONFIG words once the engine has run USER instructions
post-arm (the BK-76 ever_user latch — boot/config-phase stores stay
lawful). Scope locked (_BK41_LOCKED_WORDS): KFAULT_PC 8193, KSYS_PC 8194,
BOX0_LO/HI 8195/8196, BOX1_LO/HI 8197/8198, BOX2_LO/HI 8202/8203,
KTICK_PC 8207, TIMER_COUNT 8208, TIMER_RELOAD 8209.
MEASURED SCOPE AMENDMENT (BK41_DESIGN_NOTES.md, probe-measured; filed in
the directive's receipt appendix, never a silent edit): MODE_LATCH 8192
and TILE_ROW/H/W 8280..8283 are EXCLUDED — the landed xv6-nano S6/S11
schedulers re-arm them post-USER from SUPER at every context switch
(S11 writes 8192+8280 post-USER; the run only halts cleanly WITH those
stores). Locking them = a lawful write caught in the net = a scope error
per the directive's own rule 4. SYS_A0/A1 (8205/8206) and the INPUT ring
stay guest-writable (BK-76 §0 boundary, xv6-nano syscall_dispatch).

Refusal semantics = BK-76 Option A PER ARM: store dropped, faulted=True,
reason mmio_exemption_refused, running stopped, NO vector.

Arms covered (measured pre-fix shapes in the landing commit):
  - :968 SUPER exemption ST arm       (holes C6/C7: landed clean at HEAD
    0f8d904e — TIMER_COUNT 4242, BOX0_LO 0-over-0)
  - SUPER post-USER PARALLEL_ST arm   (hole A1: 4242 landed clean —
    probe_bk41_arms2; the box consult is USER-only so the in-window
    SUPER op rode straight through)
  USER arms (ST/PARALLEL_ST) were already closed: item-29's out-of-box
  E-K1 trap + BK-39's write_arm_fence (C1..C5 refused pre-fix).

Legs:
  L1  armed-KSYS hostile control: SUPER handler ST of sentinel to
      out-of-tile RAM word 176 still LANDS (E-K2 dispatch itself is not
      BK-41's target; the lock is config-words-only, never a blanket
      SUPER write ban). Anchor for the row's L1 wording.
  L2  disarm leg: USER PARALLEL_ST 0 into KSYS_PC 8194 traps
      (BK-39 write_arm_fence live — posture not guest-defeatable).
  L3  self-arm leg: USER PARALLEL_ST 393216 into KSYS_PC 8194 traps
      (no guest-minted USER->SUPER escape; RED pre-BK-39).
  L4  kernel-owned benign dispatch control: pre-USER SUPER seeding of
      KSYS_PC + handler dispatch still runs the handler (boot-phase
      config lawful; the ever_user latch never fires pre-USER).
  L5  non-vacuity: neutering the two BK-41 consults in a TEMP-COPY
      module reproduces the pre-fix shape (C6 sentinel lands clean);
      real tree md5-pinned before/after.
  L6  family: BK-76 oracle gate + item-29 containment + BK-39 fence
      gates green on this tree (never weaken a live guard).
  L7  arm coverage: refusal holds at BOTH arms with a nonzero sentinel —
      L7a SUPER exemption ST to TIMER_COUNT refused; L7b SUPER
      post-USER PARALLEL_ST to TIMER_COUNT refused (the measured hole);
      L7c boundary: SYS_A0 (8205) SUPER store still lands (scope not
      widened past the directive).
  L8  boundary: USER in-tile stores unaffected + SYS_A0/A1/INPUT ring
      stay guest-writable USER-side (BK-76 §0 preserved; block not
      widened).

RED-first at landing time: C6 (L7a) and A1 (L7b) measured GREEN-hole at
mainline HEAD 0f8d904e (sentinel landed, exit 0, faulted=False — probe
pasted in the landing commit). Gate run against UNFIXED tree fails
L7a/L7b with those exact shapes.
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
    GlyphAssemblerV2, OpcodeMapV2,
    KFAULT_PC_ADDR, KSYS_PC_ADDR, TIMER_COUNT_ADDR, BOX0_LO_ADDR,
    SYS_A0_ADDR, SYS_A1_ADDR, INPUT_CURSOR_ADDR,
)
from tools.glyph_process import GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
WORD_KFAULT = KFAULT_PC_ADDR >> 2      # 8193
WORD_KSYS = KSYS_PC_ADDR >> 2          # 8194
WORD_TCOUNT = TIMER_COUNT_ADDR >> 2    # 8208
WORD_BOX0LO = BOX0_LO_ADDR >> 2        # 8195
WORD_SYS_A0 = SYS_A0_ADDR >> 2         # 8205
WORD_SYS_A1 = SYS_A1_ADDR >> 2         # 8206
WORD_INPUT_CURSOR = INPUT_CURSOR_ADDR >> 2  # 8285
OUT_TILE_WORD = 176                    # plain RAM, outside the tile
SENTINEL = 4242                        # the measured C6/A1 value
GADGET_PACKED = (6 << 16) | 0          # pixel row 6, col 0 = instr 0
TILE = (5, 0, 8, 8)                    # item-29 spawn posture
REAPER_ROW = 30


def _run_lines(lines, tile=TILE, pre=None, canvas_rows=32):
    """Bake + spawn + run (the landed GlyphProcessTable.spawn(tile=...)
    harness). Verdicts from readback, never stdout."""
    img = GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)
    canvas = np.zeros((canvas_rows, 32, 3), dtype=np.uint8)
    canvas[0:img.shape[0]] = img
    return _run_canvas(canvas, tile=tile, pre=pre)


def _run_canvas(canvas, tile=TILE, pre=None):
    """Spawn + run an ALREADY-BAKED canvas (the super_case attack shape:
    USER text rows 0..1 + SUPER gadget pixels at row 6 in ONE image)."""
    table = GlyphProcessTable()
    kw = {} if tile is None else {"tile": tile, "reaper_row": REAPER_ROW}
    pid = table.spawn(image=canvas.copy(), **kw)
    cpu = table.tasks[pid]["cpu"]
    if pre:
        pre(cpu)
    table._run_task(pid)
    task = table.tasks[pid]
    return {
        "exit": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "reason": (cpu.fault_reason or ""),
        "running": bool(cpu.running),
        "mode": "USER" if cpu.mode == 1 else "SUPER",
        "output": [int(v) for v in cpu.output],
        "words": {
            "ksys": int(cpu.memory[WORD_KSYS]),
            "tcount": int(cpu.memory[WORD_TCOUNT]),
            "box0lo": int(cpu.memory[WORD_BOX0LO]),
            "sys_a0": int(cpu.memory[WORD_SYS_A0]),
            "sys_a1": int(cpu.memory[WORD_SYS_A1]),
            "input_cursor": int(cpu.memory[WORD_INPUT_CURSOR]),
            "out_tile": int(cpu.memory[OUT_TILE_WORD]),
        },
    }


def _run(lines, tile=TILE, pre=None, canvas_rows=32):
    return _run_lines(lines, tile=tile, pre=pre, canvas_rows=canvas_rows)


def _super_case(gadget_lines, pre=None):
    """USER text SYSCALLs into a KSYS-armed SUPER handler whose pixels
    are `gadget_lines` (the measured C6/C7/A1 attack shape). ONE canvas:
    USER rows 0..1, gadget pixels at row 6."""
    gadget = GlyphAssemblerV2(OM).assemble(gadget_lines, width_instrs=8)
    canvas = np.zeros((32, 32, 3), dtype=np.uint8)
    canvas[0:2] = GlyphAssemblerV2(OM).assemble(
        ["LDI r17 2", "SYSCALL r10 2", "HALT"], width_instrs=8)[0:2]
    canvas[6:6 + gadget.shape[0]] = gadget

    def _pre(cpu):
        cpu.memory[WORD_KSYS] = GADGET_PACKED
        cpu.memory[WORD_KFAULT] = REAPER_ROW << 16
        if pre:
            pre(cpu)

    return _run_canvas(canvas, pre=_pre)


# ---------------------------------------------------------------- L1
def test_l1_armed_posture_hostile_gadget_control():
    """The E-K2 armed dispatch itself is NOT the target: a SUPER handler
    storing a sentinel to plain out-of-tile RAM (word 176) still lands.
    The lock is config-words-only — never a blanket SUPER write ban."""
    r = _super_case(["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 %d" % 0xC0FFEE,
                     "ST r2 r3", "HALT"])
    assert r["exit"] == 0 and not r["faulted"], r
    assert r["words"]["out_tile"] == 0xC0FFEE, r["words"]


# ---------------------------------------------------------------- L2
def test_l2_disarm_leg_traps():
    """USER PARALLEL_ST 0 into KSYS_PC 8194 (the BK-39 disarm primitive)
    must trap — the posture is not guest-defeatable."""
    r = _run(["LDI r2 %d" % WORD_KSYS, "LDI r3 0",
              "PARALLEL_ST r2 r3 1", "HALT"])
    assert r["faulted"], r
    assert "write_arm_fence" in r["reason"], r["reason"]
    assert r["words"]["ksys"] == 0, r["words"]  # nothing landed


# ---------------------------------------------------------------- L3
def test_l3_self_arm_leg_traps():
    """USER PARALLEL_ST of 393216 (= 6<<16, the gadget packing) into
    KSYS_PC itself must trap — no guest-minted USER->SUPER escape."""
    r = _run(["LDI r2 %d" % WORD_KSYS, "LDI r3 %d" % GADGET_PACKED,
              "PARALLEL_ST r2 r3 1", "HALT"])
    assert r["faulted"], r
    assert "write_arm_fence" in r["reason"], r["reason"]
    assert r["words"]["ksys"] == 0, r["words"]


# ---------------------------------------------------------------- L4
def test_l4_kernel_owned_benign_dispatch_control():
    """Boot-phase SUPER config stays lawful: a never-USER engine seeds
    KSYS_PC + dispatches; the handler runs and stores to plain RAM.
    (The ever_user latch is what makes the lock bite — pre-USER it must
    not exist.)"""
    r = _run(["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 %d" % 0xB0B,
              "ST r2 r3", "HALT"], tile=None)
    assert r["exit"] == 0 and not r["faulted"], r
    assert r["words"]["out_tile"] == 0xB0B, r["words"]


# ---------------------------------------------------------------- L5
def test_l5_non_vacuity_neutered_lock_reproduces_prefix():
    """Neuter BOTH BK-41 consults in a TEMP-COPY module -> the C6 shape
    reproduces pre-fix (sentinel lands at TIMER_COUNT clean). Real tree
    md5-pinned before/after."""
    real = REPO / "tools" / "glyph_isa_v2.py"
    md5_before = hashlib.md5(real.read_bytes()).hexdigest()
    src = real.read_text()
    # Neuter = EMPTY the BK-41 lock set in a TEMP-COPY module. Both BK-41
    # consult arms gate on membership in _BK41_LOCKED_WORDS, so an empty
    # frozenset kills exactly this landing's consults while leaving BK-76's
    # _BK76_LOCKED_WORDS (KFAULT/KSYS/KTICK) intact — the neuters are
    # per-feature, not a blanket refusal kill. (The BK-76 EX-L5
    # early-return-inside-the-refusal style is WRONG here and was measured
    # failing: both consult sites own an unconditional `return False` after
    # the refuse call, so a no-op'd refusal still drops the store and
    # freezes PC — the sentinel can never land and the leg burns
    # max_instructions. The landed EX-L5 never hit this because its
    # hand-built CPU (arm_tile, no spawn) never sets _tile_confinement, so
    # its consult was inert for a different reason — lesson filed in the
    # landing receipt. The gate ROT-CHECK note in BK41_DESIGN_NOTES.md
    # carries the same caveat.)
    marker = "_BK41_LOCKED_WORDS = frozenset({"
    assert marker in src, "BK-41 lock-set marker missing — gate rot"
    end = src.index("})", src.index(marker)) + 2
    neutered = (src[:src.index(marker)]
                + "_BK41_LOCKED_WORDS = frozenset()  # NEUTERED (BK41 L5)"
                + src[end:])
    assert neutered != src
    assert "_BK76_LOCKED_WORDS = frozenset({" in neutered, (
        "BK-76 vector lock must SURVIVE the neuter — L5 must prove BK-41's "
        "teeth, not the absence of every lock")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "glyph_isa_v2_neutered.py"
        tmp.write_text(neutered)
        spec = importlib.util.spec_from_file_location("bk41_neutered", tmp)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        om = mod.OpcodeMapV2(wordbase_path=REPO / "db" / "wordbase.db")
        gadget = mod.GlyphAssemblerV2(om).assemble(
            ["LDI r2 %d" % WORD_TCOUNT, "LDI r3 %d" % SENTINEL,
             "ST r2 r3", "HALT"], width_instrs=8)
        canvas = np.zeros((32, 32, 3), dtype=np.uint8)
        canvas[0:2] = mod.GlyphAssemblerV2(om).assemble(
            ["LDI r17 2", "SYSCALL r10 2", "HALT"], width_instrs=8)[0:2]
        canvas[6:6 + gadget.shape[0]] = gadget
        # The table module's _TaskExitStatus subclasses the REAL engine;
        # point glyph_process's engine bindings at the neutered module so
        # the spawned CPU runs the neutered step. The neutered subclass
        # is rebuilt from source-level super() semantics by copying the
        # class body — the copied __init__ closes over the REAL
        # GlyphCPUv2 via its globals, so build it against the neutered
        # base explicitly (super(type, obj) requires a true subtype).
        from tools import glyph_process as _gp
        saved = (_gp.GlyphCPUv2, _gp._TaskExitStatus)
        _gp.GlyphCPUv2 = mod.GlyphCPUv2

        class _TaskExitStatusNeutered(mod.GlyphCPUv2):
            def __init__(self, *args, **kwargs):
                mod.GlyphCPUv2.__init__(self, *args, **kwargs)
                self.exit_status = None
                self._on_exit = None

            def _handle_syscall(self, syscall_num, image, imm=0):
                rc = mod.GlyphCPUv2._handle_syscall(
                    self, syscall_num, image, imm)
                if syscall_num == 0x05 and self._on_exit is not None:
                    self._on_exit(rc)
                return rc

        _gp._TaskExitStatus = _TaskExitStatusNeutered
        try:
            table = _gp.GlyphProcessTable()
            pid = table.spawn(image=canvas.copy(), tile=TILE,
                              reaper_row=REAPER_ROW)
            cpu = table.tasks[pid]["cpu"]
            cpu.memory[WORD_KSYS] = GADGET_PACKED
            cpu.memory[WORD_KFAULT] = REAPER_ROW << 16
            table._run_task(pid)
        finally:
            (_gp.GlyphCPUv2, _gp._TaskExitStatus) = saved
        landed = int(cpu.memory[WORD_TCOUNT])
    assert md5_before == hashlib.md5(real.read_bytes()).hexdigest(), \
        "real engine mutated by L5"
    assert landed == SENTINEL, (
        f"L5 NON-VACUITY FAILURE — neutered lock STILL refuses "
        f"(tcount={landed}); the live gate cannot fail")
    assert not cpu.faulted, cpu.fault_reason


# ---------------------------------------------------------------- L6
def test_l6_family_gates_green():
    """BK-76 oracle + BK-39 fence gates green on this tree (never weaken
    a live guard). item-29's gate joins at the post-commit family step
    (its N1 leg pins the engine byte-identical to HEAD — it cannot hold
    while this worktree carries the BK-41 engine change)."""
    for gate in ("tests/test_bk76_exemption_refusal.py",
                 "tests/test_bk39_write_fence.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=900, cwd=str(REPO))
        assert p.returncode == 0, f"{gate} RED:\n{p.stdout[-2000:]}"


# ---------------------------------------------------------------- L7
def test_l7a_super_exemption_st_tcount_refused():
    """C6 with a NONZERO sentinel: SUPER post-SYSCALL handler ST of
    4242 to TIMER_COUNT 8208 -> refused (Option A, no vector, stop).
    RED pre-BK-41: 4242 landed, exit 0, faulted=False."""
    r = _super_case(["LDI r2 %d" % WORD_TCOUNT, "LDI r3 %d" % SENTINEL,
                     "ST r2 r3", "HALT"])
    assert r["words"]["tcount"] == 0, (
        f"L7a REFUSAL FAILED — sentinel LANDED at TIMER_COUNT "
        f"(tcount={r['words']['tcount']}) through the SUPER exemption")
    assert r["faulted"] and "mmio_exemption_refused" in r["reason"], r
    assert not r["running"], r
    assert 52 not in r["output"], r


def test_l7b_super_parallel_st_tcount_refused():
    """The measured A1 hole: SUPER post-USER PARALLEL_ST of 4242 to
    TIMER_COUNT -> refused at the BK-39 arm (box consult is USER-only;
    without the BK-41 consult the in-window SUPER op rode through).
    RED pre-BK-41: 4242 landed, exit 0, faulted=False."""
    r = _super_case(["LDI r2 %d" % WORD_TCOUNT, "LDI r3 %d" % SENTINEL,
                     "PARALLEL_ST r2 r3 1", "HALT"])
    assert r["words"]["tcount"] == 0, (
        f"L7b REFUSAL FAILED — sentinel LANDED at TIMER_COUNT via "
        f"SUPER PARALLEL_ST (tcount={r['words']['tcount']})")
    assert r["faulted"] and "mmio_exemption_refused" in r["reason"], r
    assert not r["running"], r


def test_l7c_scope_boundary_sys_a0_super_store_lands():
    """Scope NOT widened: a SUPER handler store to SYS_A0 (8205 — the
    xv6-nano ISO_SYS_A0 site) still lands; run continues."""
    r = _super_case(["LDI r2 %d" % WORD_SYS_A0, "LDI r3 %d" % SENTINEL,
                     "ST r2 r3", "PRT r3", "SYSRET",
                     "LDI r5 52", "PRT r5", "HALT"])
    assert r["words"]["sys_a0"] == SENTINEL, (
        f"L7c SCOPE BREACH — lawful ISO_SYS_A0 SUPER store refused "
        f"(sys_a0={r['words']['sys_a0']})")
    assert not r["faulted"] and r["exit"] == 0, r


# ---------------------------------------------------------------- L8
def test_l8_user_boundary_words_stay_guest_writable():
    """BK-76 §0 boundary preserved: a tiled USER task can still store to
    SYS_A0/A1 and INPUT_CURSOR (8205/8206/8285) — the config lock did not
    swallow the data words. Tile = (256, 12, 2, 8): covers MMIO words
    8192..8447 (word-grid rows 256..257) but NOT the forbidden vectors —
    and, critically, these stores are LAWFUL (no fence consult should
    fire on them; the E-K1 predicate covers them via the tile). This is
    the BK-76 oracle gate's own containment posture (tile=(256,19,1,2)).
    L8b: MODE_LATCH/TILE re-arm words (8192, 8280) are NOT in the locked
    set — asserted from the module constant so the xv6-nano S6/S11
    lawful re-arm path stays structural, not accidental."""
    # tile covers word-grid rows 256..257 x cols 12..19: words 8204..8231
    r = _run(["LDI r2 %d" % WORD_SYS_A0, "LDI r3 111", "ST r2 r3",
              "LDI r2 %d" % WORD_SYS_A1, "LDI r3 222", "ST r2 r3",
              "HALT"], tile=(256, 12, 2, 8))
    w = r["words"]
    assert not r["faulted"] and r["exit"] == 0, r
    assert w["sys_a0"] == 111 and w["sys_a1"] == 222, w
    # INPUT_CURSOR 8285 (row 258) is outside that tile; use the whole
    # MMIO-block-covering tile (255, 0, 5, 32) instead — rows 255..259
    # cover words 8160..8319 (config block + input ring head).
    r2 = _run(["LDI r2 %d" % WORD_INPUT_CURSOR, "LDI r3 333", "ST r2 r3",
               "HALT"], tile=(255, 0, 5, 32))
    assert not r2["faulted"] and r2["words"]["input_cursor"] == 333, r2
    import tools.glyph_isa_v2 as eng
    locked = eng.GlyphCPUv2._BK41_LOCKED_WORDS
    assert (eng.MODE_LATCH_ADDR >> 2) not in locked
    assert (eng.TILE_ROW_ADDR >> 2) not in locked
    assert WORD_SYS_A0 not in locked
    assert WORD_SYS_A1 not in locked
    assert WORD_INPUT_CURSOR not in locked


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
