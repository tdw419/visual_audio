#!/usr/bin/env python3
"""BK-44 gate — FS-allow posture guard: GLYPH_FS_ALLOW roots bound 0x03
FILE_WRITE and 0x04 FILE_READ host arms (row: systems/GLYPH_BACKLOG.md
BK-44; sequenced fence commit step 6).

DEFECT (measured at HEAD 07eefcc2, probe .builder_queue/probe_bk44_red_af3e.py,
md5 7a268057e72bd67f7f00e8d9f301dc09, 3 runs deterministic): BK-15's
containment rationale ("enumeration is the more invasive primitive, it must
not be cheaper to reach than RUN", glyph_isa_v2.py:577-579) was INVERTED —
under the identical empty env in one process, 0x13 FILE_LIST '/tmp/b8' was
refused (rc -1, dest zero) while the SAME tiled USER task WROTE '/tmp/b9'
(host file b'WX', rc 0) and READ '/tmp/ba' (b'AUTUMN' into guest RAM, rc 6):
the two primitives that destroy/overwrite host files and exfiltrate host
file CONTENT were strictly cheaper to reach than the one that only names
files. The older research probe (probe_fs_allow_asym_af3e.py, HEAD
d61dc186) no longer measures the raw shape — the landed BK-39/40/42 fences
trap its word-168 staging before any syscall verdict; the RED probe re-
files with the current geometry (staging run 192..199, dest run 224..231).

FIX (tools/glyph_isa_v2.py, glyph_dispatch mirror byte-identical): the 0x03
and 0x04 HOST arms consult _get_fs_allow_roots() — realpath under a root
or refuse with rc -1 — exactly the 0x13 arm's landed check (BK-15),
deny-by-default, placed AFTER the item-25 VFS reroute so VFS-attached
writes/reads keep the VFS's own containment and never hit the host check.
No new dispatch-site consult: this is handler-posture parity, not a fence
term. 0x07/0x12 RUN keep GLYPH_RUN_ALLOW; 0x08/0x09 AUDIO arms and 0x01
WRITE stay out of scope (separate class, per the row).

Legs:
  L1  0x03 with env unset -> refused (rc -1 in rd), NO host file, clean
      exit (handler-level refusal, not a fault — the 0x13 posture).
  L2  0x04 with env unset -> refused (rc -1), guest RAM untouched.
  L3  0x13 env-unset refusal stays green (BK-15 baseline, never weakened).
  L4  0x03/0x04/0x13 under a leg-scoped allow root all succeed
      (non-vacuity: the check must not brick legit use; roots match
      realpaths, not raw strings).
  L5  ST out-of-tile trap control (fault_addr = word*4, E-K1 baseline
      intact; the fence family is untouched by this landing).
  L6  non-vacuity — the new consults neutered (instance shadow on the
      module-level _get_fs_allow_roots the HANDLER closes over is not
      possible — it reads the module global at call time, so the leg
      monkeypatches the MODULE attribute; engine file untouched on disk,
      md5-pinned) -> L1's exact program writes the host file clean (the
      measured pre-fix shape reproduced).
  L7  family — BK-42 + BK-40 + BK-41 + BK-39 + BK-15 gates green on this
      tree (never weaken a live guard) + engine mirror md5 parity.

Env isolation: GLYPH_FS_ALLOW is process-global — saved/restored around
every leg (probe + BK-40 L3 precedent). Fixture paths are 6-char + NUL so
staging fits the in-tile run 192..199 (BK-42 geometry; longer paths cross
the run boundary and trip the landed BK-39 staging fence).

RED-first at landing time (engine fix stashed): L1 fails (host file b'WX'
lands, rc 0 clean), L2 fails ('AUTUMN' lands, rc 6), L6 passes pre-fix BY
CONSTRUCTION (consult absent == neutered; md5-pinned). L3/L4/L5 pass
(harness live). Fix applied -> 7/7.

What the PASS does NOT prove: VFS-attached legs beyond the reroute-order
source read (no VFS device in this harness — item-25's own gate owns
those), 0x01 WRITE / 0x08/0x09 AUDIO windows (separate class per the row),
the WGSL twin (host-FS syscalls are oracle-Python-only; the twin's 0x03/
0x04 are honest no-op stubs — test_defect_d pins that and is unaffected),
symlink-escape content beyond realpath (roots match realpaths; TOCTOU
between the check and open() is out of scope — single-threaded handler),
allowlist CONTENT policy beyond deny-by-default (the operator chooses
roots; this gate pins only the mechanism).
"""
import hashlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import pytest  # noqa: E402

import tools.glyph_isa_v2 as eng  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, OpcodeMapV2, W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
OUT_TILE_WORD = TILE_ROW * W_MEM + TILE_COL + TILE_W   # 168: first OUT word
STAGE_WORD = 192                                        # in-tile run (path)
DATA_WORD = 224                                         # in-tile run 2
RC_WORD = 231                                           # in-tile, past blobs

_ENGINE_PATH = REPO / "tools" / "glyph_isa_v2.py"
_ENGINE_MD5 = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()

_ENV = "GLYPH_FS_ALLOW"


def _stage(word, data: bytes, term=True):
    out = []
    for i, b in enumerate(data):
        out += ["LDI r5 %d" % (word + i), "LDI r6 %d" % b,
                "PARALLEL_ST r5 r6 1"]
    if term:
        out += ["LDI r5 %d" % (word + len(data)), "LDI r6 0",
                "PARALLEL_ST r5 r6 1"]
    return out


def _prog(sysnum, r2, r3, path: bytes):
    lines = _stage(STAGE_WORD, path)
    lines += ["LDI r1 %d" % STAGE_WORD,
              "LDI r2 %d" % r2,
              "LDI r3 %d" % r3,
              "SYSCALL r10 %d" % sysnum,
              "LDI r2 %d" % RC_WORD,
              "ST r2 r10",
              "HALT"]
    return lines


def _run(prog, env, seed=None):
    """Assemble, spawn tiled, seed RAM, set/clear GLYPH_FS_ALLOW, wait.
    Returns (rc, cpu, syscall_rc)."""
    img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk44", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    for addr, val in (seed or {}).items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    old = os.environ.get(_ENV)
    try:
        if env is None:
            os.environ.pop(_ENV, None)
        else:
            os.environ[_ENV] = env
        rc = table.wait(pid)
    finally:
        if old is None:
            os.environ.pop(_ENV, None)
        else:
            os.environ[_ENV] = old
    return rc, cpu, int(cpu.memory[RC_WORD]) & 0xFFFFFFFF


def _unique_tmp(name) -> Path:
    """Leg-scoped dir under /tmp: short (6-char paths fit the run),
    unique per test (no cross-leg fixture coupling)."""
    d = Path("/tmp") / name
    d.mkdir(exist_ok=True)
    return d


def _syscall_rc_signed(v: int) -> int:
    return v - (1 << 32) if v >= (1 << 31) else v


# FIXTURE PATH BUDGET (the BK-42 geometry law, re-bitten by this gate's
# own first run): the in-tile staging run is 8 words (192..199), so path
# + NUL must fit 8 bytes — every fixture path below is EXACTLY 7 chars.
# The armed root for the allow legs is "/tmp" (the BK-40 L3 / BK-42
# migration precedent); determinism comes from private 7-char fixture
# dirs, not from deep unique paths (a deeper path cannot fit the run and
# the landed BK-39 staging fence refuses the write at word 200).

FW_PATH = "/tmp/p1"      # L1/L6 host write target
FR_PATH = "/tmp/p2"      # L2/L4 host read fixture
LIST_DIR = "/tmp/p3"     # L3/L4 private listing dir (one entry "k1")
ARM_ROOT = "/tmp"


def _rm(p: str):
    try:
        os.unlink(p)
    except OSError:
        pass
    try:
        os.rmdir(p)   # leftover EMPTY dir from a previous run/host state
    except OSError:
        pass


def _absent(p: str):
    """Pre-leg hygiene: the fixture path must not exist (a pre-existing
    file OR directory would poison the no-landing asserts)."""
    _rm(p)
    assert not os.path.exists(p), f"fixture path occupied: {p}"


# ── L1: 0x03 with env unset -> refused, NO host file ─────────────────────
def test_l1_fw_no_env_refused():
    """RED at 07eefcc2: host file b'WX' landed, syscall rc 0, clean exit —
    the measured pre-fix shape. Post-fix: handler refuses (rc -1 in rd),
    no file, clean exit (handler-level posture, not a fault)."""
    _absent(FW_PATH)
    prog = _prog(3, DATA_WORD, 2, FW_PATH.encode())
    seed = {DATA_WORD: 0x57, DATA_WORD + 1: 0x58, RC_WORD: 0}
    rc, cpu, src = _run(prog, None, seed)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)      # refusal, not a fault
    assert _syscall_rc_signed(src) == -1, hex(src)     # the refusal rc
    assert not os.path.exists(FW_PATH), "host file LANDED with env unset"
    assert not cpu.faulted, cpu.fault_reason
    _absent(FW_PATH)


# ── L2: 0x04 with env unset -> refused, RAM untouched ────────────────────
def test_l2_fr_no_env_refused():
    """RED at 07eefcc2: b'AUTUMN' landed in guest RAM, rc 6. Post-fix:
    rc -1, guest RAM untouched."""
    with open(FR_PATH, "wb") as f:
        f.write(b"AUTUMN")
    prog = _prog(4, DATA_WORD, 7, FR_PATH.encode())
    seed = {DATA_WORD: 0, RC_WORD: 0}
    rc, cpu, src = _run(prog, None, seed)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert _syscall_rc_signed(src) == -1, hex(src)
    assert int(cpu.memory[DATA_WORD]) == 0, "host bytes LANDED (pre-fix shape)"
    _rm(FR_PATH)


# ── L3: 0x13 env-unset refusal stays green (BK-15 baseline) ──────────────
def test_l3_list_baseline_intact():
    """The BK-15 refusal must survive this landing untouched (never weaken
    a live guard)."""
    os.makedirs(LIST_DIR, exist_ok=True)
    (Path(LIST_DIR) / "k1").write_bytes(b"x")
    prog = _prog(19, DATA_WORD, 7, LIST_DIR.encode())
    seed = {DATA_WORD: 0, RC_WORD: 0}
    rc, cpu, src = _run(prog, None, seed)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert _syscall_rc_signed(src) == -1, hex(src)
    assert int(cpu.memory[DATA_WORD]) == 0
    (Path(LIST_DIR) / "k1").unlink()
    os.rmdir(LIST_DIR)


# ── L4: leg-scoped allow root -> all three host arms succeed ─────────────
def test_l4_scoped_allow_all_arms():
    """Non-vacuity: the root check must not brick legit use. Roots match
    REALPATHS (/tmp may be a symlink — the 0x13 arm compares
    realpath-to-root), so the env carries the resolved root."""
    os.makedirs(LIST_DIR, exist_ok=True)
    (Path(LIST_DIR) / "k1").write_bytes(b"x")
    _absent(FW_PATH)
    _absent(FR_PATH)
    with open(FR_PATH, "wb") as f:
        f.write(b"AUTUMN")
    env = ARM_ROOT
    # 0x03 under its root
    rc, cpu, src = _run(_prog(3, DATA_WORD, 2, FW_PATH.encode()), env,
                        {DATA_WORD: 0x57, DATA_WORD + 1: 0x58, RC_WORD: 0})
    assert rc == EXIT_OK and _syscall_rc_signed(src) == 0, (rc, hex(src))
    assert open(FW_PATH, "rb").read() == b"WX"
    # 0x04 under its root
    rc, cpu, src = _run(_prog(4, DATA_WORD, 7, FR_PATH.encode()), env,
                        {DATA_WORD: 0, RC_WORD: 0})
    assert rc == EXIT_OK and _syscall_rc_signed(src) == 6, (rc, hex(src))
    assert int(cpu.memory[DATA_WORD]) == ord("A")
    # 0x13 under its root (same env, same process model)
    rc, cpu, src = _run(_prog(19, DATA_WORD, 7, LIST_DIR.encode()), env,
                        {DATA_WORD: 0, RC_WORD: 0})
    assert rc == EXIT_OK and _syscall_rc_signed(src) == 1, (rc, hex(src))
    assert int(cpu.memory[DATA_WORD]) == ord("k")
    _rm(FW_PATH)
    _rm(FR_PATH)
    (Path(LIST_DIR) / "k1").unlink()
    os.rmdir(LIST_DIR)


# ── L5: ST out-of-tile trap control (E-K1 baseline intact) ───────────────
def test_l5_st_out_of_tile_control():
    prog = ["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 4660", "ST r2 r3", "HALT"]
    rc, cpu, _ = _run(prog, None)
    assert rc == EXIT_FAULT, rc
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4


# ── L6: non-vacuity — consult neutered, pre-fix shape returns ────────────
def test_l6_non_vacuity():
    """The module-level _get_fs_allow_roots is read at handler call time,
    so monkeypatching the MODULE attribute neuters the new checks (the
    0x13 arm rides the same global — its baseline is L3's subject; the
    leg proves the checks are LOAD-BEARING, not that each site is
    separately wired; L1/L2 vs L3/L4 site coverage pins the wiring).
    Engine file untouched on disk, md5-pinned before/after. Env stays
    UNSET through the leg: only the neutered global can admit the path,
    so a landed file proves the consult was the refusing site."""
    md5_before = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()
    _absent(FW_PATH)
    saved = eng._get_fs_allow_roots
    eng._get_fs_allow_roots = lambda: {"/tmp"}
    try:
        prog = _prog(3, DATA_WORD, 2, FW_PATH.encode())
        seed = {DATA_WORD: 0x57, DATA_WORD + 1: 0x58, RC_WORD: 0}
        rc, cpu, src = _run(prog, None, seed)
        md5_after = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()
        assert md5_before == md5_after == _ENGINE_MD5, (md5_before, md5_after)
        assert rc == EXIT_OK, (rc, cpu.fault_reason)
        assert _syscall_rc_signed(src) == 0, hex(src)
        assert os.path.exists(FW_PATH) and open(FW_PATH, "rb").read() == b"WX", (
            "pre-fix shape NOT reproduced — non-vacuity leg vacuous")
    finally:
        eng._get_fs_allow_roots = saved
        _rm(FW_PATH)


# ── L7: family — fence gates + BK-15 + engine mirror parity ──────────────
def test_l7_family():
    for gate in ("tests/test_bk42_fw_exfil_fence.py",
                 "tests/test_bk40_syscall_fence.py",
                 "tests/test_bk41_ksys_fence.py",
                 "tests/test_bk39_write_fence.py",
                 "tests/test_bk15_file_list.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert p.returncode == 0, (gate, p.stdout[-2000:])
    mirror = REPO / "glyph_dispatch" / "src" / "glyph" / "glyph_isa_v2.py"
    assert hashlib.md5(mirror.read_bytes()).hexdigest() == _ENGINE_MD5, (
        "engine mirror drift")


def _cleanup_dir(d: Path):
    for f in d.iterdir():
        f.unlink()
    d.rmdir()
