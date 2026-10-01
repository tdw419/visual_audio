#!/usr/bin/env python3
"""BK-43 gate — RUN path/argv fence guard (step 5 of the sequenced fence
commit; row: systems/GLYPH_BACKLOG.md BK-43).

DEFECT (measured at HEAD 6677603b, probe .builder_queue/probe_run_arg_af3e.py,
md5 e238a3ab4ebbfbdbdb4f94dd45cfeb09): 0x07/0x12 DO check the target's
realpath against GLYPH_RUN_ALLOW (deny-by-default), but the string they check
is assembled by the same fence-blind _read_path BK-42 convicted, and 0x12
RUN2's argv args are documented "data, not targets" — no consult of any kind:
  (1) path smuggle — in-tile '/tmp/run' (NO NUL in tile), out-of-tile
      'r5r5\\0' -> _read_path decoded '/tmp/runr5r5', allowlist PASSED, the
      runner EXECUTED: which binary runs was decided by bytes the task
      cannot lawfully address;
  (2) argv leak — 0x12 arg1_addr OUT-of-tile seeded 'SRC5\\0' -> host marker
      contains exactly ARG1=[SRC5]: out-of-tile RAM crossed execve().

POSTURE at landing: BK-42's landed _bk42_path_fault already consults the
PATH argument (r1) of every path-taking syscall INCLUDING 0x07/0x12 (the
smuggle channel of the probe is dead: an unterminated in-tile path decodes
nowhere). What remained open is the 0x12 RUN2 ARGV windows: r2=arg1_addr,
r3=arg2_addr are decoded by _read_path at the handler (glyph_isa_v2.py RUN2
arm) with no fence consult — the argv channel still carried out-of-tile RAM
through execve(). The fix adds GlyphCPUv2._bk43_argv_fault(addr): the argv
decode (same walk as _read_path — FS-pixel alias arm admitted, past-RAM
break, 4096 ceiling) must stay inside the fence term _addr_in_box; the first
out-of-fence word refuses the WHOLE syscall via the landed E-K1 tail
(_stack_fence_fault: fault_addr = word<<2, packed fault_pc, mode->SUPER,
KFAULT_PC vector, kf==0 stop), consulted at the SYSCALL dispatch site BEFORE
the handler runs. addr==0 ("no argument") admits. Reason tag
`argv_decode_fence`. Term set identical to every landed consult: USER +
_tile_confinement + _iso_enabled; SUPER (E-K2 dispatch) and unfenced tasks
untouched. General LD stays governed by RULING_BK38_READ_POSTURE — this
gate fences syscall ARGUMENT windows only.

Legs:
  L1  path smuggle shape: in-tile '/tmp/run' NO NUL, out-of-tile tail
      seeded -> the syscall must be REFUSED (path_decode_fence from the
      landed BK-42 consult; handler never runs, no marker file). RED at
      bf60a51f: pre-BK-42 this executed; post-BK-42 pre-BK-43 the landed
      path consult already refuses it (guard survives — never weaken a
      live guard, this leg pins it).
  L2  argv leak shape: 0x12, allowed in-tile target, arg1_addr OUT-of-tile
      seeded 'SRC5\\0' -> refused (argv_decode_fence), NO marker. RED at
      bf60a51f: ARG1=[SRC5] lands host-side (the pre-fix shape).
  L3  in-tile controls: 0x07 allowed target runs (marker written); 0x12
      with in-tile argv runs and the marker carries the in-tile argument.
  L4  deny-by-default: GLYPH_RUN_ALLOW unset -> 0x07 refused by the
      allowlist (handler-level, rc=-1, no marker) — baseline intact.
  L5  argv-0 control: arg1_addr==0 admitted (argv decode consult must not
      brick the 0x07-shaped single-arg path) + ST out-of-tile trap control
      (fault_addr = word*4, E-K1 baseline).
  L6  non-vacuity: the new consult neutered (instance attribute shadow,
      engine file untouched on disk, md5-pinned) -> L2's exact program
      lands ARG1=[SRC5] host-side (pre-fix shape reproduced).
  L7  family: BK-42 + BK-40 + BK-41 + BK-39 gates green on this tree
      (never weaken a live guard).

FIXTURE GEOMETRY (probe_bk42_geom_af3e, live _addr_in_box): the GO-2 tile
(5,0,8,8) term is Hilbert-scattered — in-tile contiguous runs are
(160..167), (192..199), (224..231), ...; 168..191 and 200..223 are OUT.
In-tile staging sits at 192..199 (BK-42 precedent); out-of-tile canaries at
168+. Runners are <= 8 bytes incl. NUL so they fit one in-tile run.

Env isolation: GLYPH_RUN_ALLOW is process-global — saved/restored around
every leg (probe precedent); markers unlinked + asserted absent pre-leg.

RED-first at landing time (engine fix stashed): L2 fails with the measured
pre-fix shape (marker ARG1=[SRC5] lands, rc=EXIT_OK); L1 passes on the
landed BK-42 consult (documented above — it pins the smuggle channel dead);
L3..L5 pass (harness live); L6 passes pre-fix BY CONSTRUCTION (consult
absent == neutered; md5-pinned before/after). Fix applied -> 7/7.

What the PASS does NOT prove: BK-44's FS-allow posture (0x03/0x04 root
checks — separate row), VFS-attached legs (no VFS device in this harness),
0x01 WRITE / 0x08/0x09 AUDIO data windows (separate class), the WGSL twin
(syscall handlers are oracle-Python-only — BK-40 precedent), allowlist
CONTENT correctness beyond deny-by-default (L4 pins the baseline only).
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, OpcodeMapV2, W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 168: first OUT word
STAGE_WORD = 192                                    # in-tile staging run

RUNNER = "/tmp/r5"
RUNNER_SMUGGLE = "/tmp/runr5r5"
MARKER = "/tmp/b43_marker"
RUNNER_BODY = "#!/bin/sh\nprintf 'ARG1=[%s]' \"$1\" > %s\n" % ("%s", MARKER)

_ENGINE_PATH = REPO / "tools" / "glyph_isa_v2.py"
_ENGINE_MD5 = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()


def _build(lines):
    return GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)


def _stage(path_addr, data: bytes, term=True):
    """Emit PARALLEL_ST staging for `data` at word `path_addr`."""
    out = []
    for i, b in enumerate(data):
        out += ["LDI r5 %d" % (path_addr + i), "LDI r6 %d" % b,
                "PARALLEL_ST r5 r6 1"]
    if term:
        out += ["LDI r5 %d" % (path_addr + len(data)), "LDI r6 0",
                "PARALLEL_ST r5 r6 1"]
    return out


def _make_runner():
    with open(RUNNER, "w") as f:
        f.write(RUNNER_BODY)
    os.chmod(RUNNER, 0o755)


def _run(prog, seed=None, allow=True, allow_extra=None):
    """Assemble, spawn tiled, seed RAM, set/clear GLYPH_RUN_ALLOW, wait."""
    _make_runner()
    for p in (MARKER,):
        if os.path.exists(p):
            os.unlink(p)
        assert not os.path.exists(p), p
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk43", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    for addr, val in (seed or {}).items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    old = os.environ.get("GLYPH_RUN_ALLOW")
    try:
        if allow:
            entries = [os.path.realpath(RUNNER)]
            for extra in (allow_extra or []):
                entries.append(os.path.realpath(extra))
            os.environ["GLYPH_RUN_ALLOW"] = ":".join(entries)
        else:
            os.environ.pop("GLYPH_RUN_ALLOW", None)
        rc = table.wait(pid)
    finally:
        if old is None:
            os.environ.pop("GLYPH_RUN_ALLOW", None)
        else:
            os.environ["GLYPH_RUN_ALLOW"] = old
    marker = open(MARKER, "rb").read() if os.path.exists(MARKER) else None
    return rc, cpu, marker


def _cleanup():
    for p in (MARKER, RUNNER, RUNNER_SMUGGLE):
        try:
            os.unlink(p)
        except OSError:
            pass


# ── L1: path smuggle shape refused (BK-42's landed consult owns it) ─────
def test_l1_path_smuggle_refused():
    """In-tile '/tmp/run' (8 bytes, NO NUL in tile), out-of-tile tail
    'r5r5' + NUL at 168..172. The smuggled target /tmp/runr5r5 IS on the
    allowlist (worst case), so the ONLY thing standing between the task
    and executing a binary whose name it cannot lawfully address is the
    path-decode fence. Pre-BK-42 this executed; the landed consult must
    keep refusing it."""
    with open(RUNNER_SMUGGLE, "w") as f:
        f.write(RUNNER_BODY)
    os.chmod(RUNNER_SMUGGLE, 0o755)
    allow = os.path.realpath(RUNNER) + ":" + os.path.realpath(RUNNER_SMUGGLE)
    prog = (
        _stage(STAGE_WORD, b"/tmp/run", term=False)   # NO NUL in tile
        + [
            "LDI r1 %d" % STAGE_WORD,
            "SYSCALL r10 7",
            "HALT",
        ]
    )
    rc, cpu, marker = _run(prog, seed={
        168: ord("r"), 169: ord("5"), 170: ord("r"), 171: ord("5"), 172: 0,
    }, allow=True, allow_extra=[RUNNER_SMUGGLE])
    assert rc == EXIT_FAULT, (rc, cpu.fault_reason)
    assert cpu.faulted, cpu.fault_reason
    assert "path_decode_fence" in (cpu.fault_reason or ""), cpu.fault_reason
    assert marker is None, "smuggled binary EXECUTED (pre-BK-42 shape)"


# ── L2: argv leak shape refused (the new BK-43 consult) ─────────────────
def test_l2_argv_out_of_tile_refused():
    """0x12 RUN2, allowed in-tile target /tmp/r5, arg1_addr = 168 (OUT of
    tile) seeded 'SRC5\\0'. RED at bf60a51f: the marker contained exactly
    ARG1=[SRC5] — out-of-tile RAM crossed execve() as ARGV. Post-fix the
    argv-decode consult refuses (argv_decode_fence) and no marker lands."""
    prog = (
        _stage(STAGE_WORD, RUNNER.encode())            # 6 chars + NUL, in tile
        + [
            "LDI r1 %d" % STAGE_WORD,
            "LDI r2 %d" % OUT_TILE_WORD,               # argv1 OUT of tile
            "LDI r3 0",
            "SYSCALL r10 18",
            "HALT",
        ]
    )
    rc, cpu, marker = _run(prog, seed={
        168: ord("S"), 169: ord("R"), 170: ord("C"), 171: ord("5"), 172: 0,
    }, allow=True)
    assert rc == EXIT_FAULT, (rc, cpu.fault_reason)
    assert cpu.faulted, cpu.fault_reason
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4
    assert "argv_decode_fence" in (cpu.fault_reason or ""), cpu.fault_reason
    assert marker is None, "argv leak LANDED (pre-fix shape): %r" % marker


# ── L3: in-tile controls stay green ──────────────────────────────────────
def test_l3_in_tile_controls():
    _make_runner()
    # 0x07 with in-tile allowed target: runs, marker written.
    prog = (
        _stage(STAGE_WORD, RUNNER.encode())
        + ["LDI r1 %d" % STAGE_WORD, "SYSCALL r10 7", "HALT"]
    )
    rc, cpu, marker = _run(prog, allow=True)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert marker is not None and marker.startswith(b"ARG1=[") , marker
    # 0x12 with IN-tile argv: runs, marker carries the in-tile argument.
    # TWO fixture constraints (both caught by this leg's own RED runs):
    # (1) ARG staging sits in the next in-tile run (224..231) — word 200 is
    #     OUT of tile (BK-42 fixture geometry; first draft faulted
    #     write_arm_fence at word 200, not an argv verdict);
    # (2) the program must stay <= 48 instructions (<= 6 image rows): the
    #     PARALLEL_ST write-through pixel mirror maps word 192 to image row
    #     6 — with a 7-row image (50 instrs) it CLOBBERS the SYSCALL/HALT
    #     at slots 48..55 (first draft halted opcode-None at (0,6) before
    #     the syscall fired). 5-byte arg keeps it at 47.
    ARG_WORD = 224
    prog2 = (
        _stage(STAGE_WORD, RUNNER.encode())
        + _stage(ARG_WORD, b"INITL")
        + [
            "LDI r1 %d" % STAGE_WORD,
            "LDI r2 %d" % ARG_WORD,
            "LDI r3 0",
            "SYSCALL r10 18",
            "HALT",
        ]
    )
    rc2, cpu2, marker2 = _run(prog2, allow=True)
    assert rc2 == EXIT_OK, (rc2, cpu2.fault_reason)
    assert marker2 == b"ARG1=[INITL]", marker2


# ── L4: deny-by-default baseline intact ─────────────────────────────────
def test_l4_deny_by_default():
    prog = (
        _stage(STAGE_WORD, RUNNER.encode())
        + ["LDI r1 %d" % STAGE_WORD, "SYSCALL r10 7", "HALT"]
    )
    rc, cpu, marker = _run(prog, allow=False)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)   # handler returns -1, no fault
    # rd receives the SIGNED -1 (engine stores signed; L4 asserts the
    # refusal rc, not a bit pattern — caught by this leg's own RED run).
    assert int(cpu.registers[10]) == -1, int(cpu.registers[10])
    assert marker is None, "deny-by-default broken"


# ── L5: arg-0 admission + ST trap control ────────────────────────────────
def test_l5_arg0_admission_and_st_control():
    """arg1_addr==0 must be ADMITTED by the argv consult (no decode), and a
    plain ST out-of-tile still traps (E-K1 baseline)."""
    prog = (
        _stage(STAGE_WORD, RUNNER.encode())
        + [
            "LDI r1 %d" % STAGE_WORD,
            "LDI r2 0",
            "LDI r3 0",
            "SYSCALL r10 18",
            "HALT",
        ]
    )
    rc, cpu, marker = _run(prog, allow=True)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert marker is not None and marker.startswith(b"ARG1=["), marker
    # ST control
    prog_st = ["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 4660", "ST r2 r3", "HALT"]
    img = _build(prog_st)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk43_l5b",
                      tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    rc_st = table.wait(pid)
    cpu_st = table.tasks[pid]["cpu"]
    assert rc_st == EXIT_FAULT, rc_st
    assert int(getattr(cpu_st, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4


# ── L6: non-vacuity — neuter the consult, pre-fix argv leak returns ─────
def test_l6_non_vacuity():
    md5_before = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()
    prog = (
        _stage(STAGE_WORD, RUNNER.encode())
        + [
            "LDI r1 %d" % STAGE_WORD,
            "LDI r2 %d" % OUT_TILE_WORD,
            "LDI r3 0",
            "SYSCALL r10 18",
            "HALT",
        ]
    )
    _make_runner()
    for p in (MARKER,):
        if os.path.exists(p):
            os.unlink(p)
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk43_l6",
                      tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    cpu._bk43_argv_fault = lambda *a, **k: None     # instance shadow only
    for addr, val in {168: ord("S"), 169: ord("R"), 170: ord("C"),
                      171: ord("5"), 172: 0}.items():
        cpu.memory[addr] = val
    old = os.environ.get("GLYPH_RUN_ALLOW")
    os.environ["GLYPH_RUN_ALLOW"] = os.path.realpath(RUNNER)
    try:
        rc = table.wait(pid)
    finally:
        if old is None:
            os.environ.pop("GLYPH_RUN_ALLOW", None)
        else:
            os.environ["GLYPH_RUN_ALLOW"] = old
    md5_after = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()
    assert md5_before == md5_after == _ENGINE_MD5, (md5_before, md5_after)
    marker = open(MARKER, "rb").read() if os.path.exists(MARKER) else None
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert marker == b"ARG1=[SRC5]", (
        "pre-fix argv-leak shape NOT reproduced — non-vacuity leg vacuous: %r"
        % marker)
    _cleanup()


# ── L7: family — BK-42 + BK-40 + BK-41 + BK-39 gates green ──────────────
def test_l7_family():
    for gate in ("tests/test_bk42_fw_exfil_fence.py",
                 "tests/test_bk40_syscall_fence.py",
                 "tests/test_bk41_ksys_fence.py",
                 "tests/test_bk39_write_fence.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert p.returncode == 0, (gate, p.stdout[-2000:])
