#!/usr/bin/env python3
"""BK-42 gate — FILE_WRITE exfil + path-decoder fence guard (step 4 of the
sequenced fence commit; row: systems/GLYPH_BACKLOG.md BK-42).

DEFECT (measured at HEAD a893ad13, probe .builder_queue/probe_fw_exfil_af3e.py,
md5 d7a9aa69260d2173fc2e61c98ef6e511): from a tiled USER task,
0x03 FILE_WRITE reads `self.memory` with no fence consult and sinks via
open(path, "wb") — full cross-fence exfil to an arbitrary HOST path; and
_read_path (shared by 0x03/0x04/0x07/0x12/0x13) decodes RAM words past the
tile boundary until NUL — the syscall PATH argument is itself a fence-blind
cross-fence READ channel (the filename IS the exfil).

POSTURE (decided at landing, consistent with the landed BK-40 consult):
per-syscall consult at the SYSCALL dispatch site, BEFORE the handler runs:
  - 0x03 FILE_WRITE: the DATA source window (r2=data_addr, r3=len,
    WORD-granular — the handler reads one byte per word) and the PATH
    staging window (r1, decoded up to and including the NUL with the same
    walk the handler will do) must both be inside the fence term
    _addr_in_box (boxes + GO-2 tile). Any out-of-fence word refuses the
    WHOLE syscall via the landed E-K1 tail (_stack_fence_fault contract:
    fault_addr = word<<2, fault_pc packed, mode->SUPER, KFAULT_PC vector,
    kf==0 stop). Handler never runs on refusal: no host file is created
    or touched. Consult reason tag: `syscall_source_fence`.
  - The shared PATH-decode consult applies to the PATH argument of ALL
    path-taking syscalls (0x03/0x04/0x07/0x08/0x09/0x12/0x13) at the same
    dispatch site: a path whose decode crosses the tile boundary with no
    in-tile NUL is refused (reason tag `path_decode_fence`). BK-43's
    RUN-smuggle shape rides this consult; its own gate re-files its legs.
USER + _tile_confinement + _iso_enabled only — the same term set as every
landed fence consult; SUPER (E-K2 dispatch) and unfenced tasks untouched.
General LD stays governed by RULING_BK38_READ_POSTURE (cooperative
read-shared model) — this gate fences syscall ARGUMENT windows only.

Legs:
  L1  0x03 FILE_WRITE data window out-of-tile -> fault, NO host file.
  L2  LD-fed shape: out-of-tile canary LD traps AT THE LD (BK-38's GO-2
      tile LD gate owns that consult); the syscall never fires; no file.
  L3  unterminated in-tile path -> the decode must NOT cross the tile;
      the pre-fix artifact (file at <path><out-of-tile bytes>) must not
      appear.
  L4  in-tile controls: FILE_WRITE in-tile data + in-tile path lands the
      file; FILE_READ in-tile path control stays green.
  L5  ST-out-of-tile trap control (fault_addr = dest*4, E-K1 baseline).
  L6  non-vacuity: the new consults neutered (instance attribute shadow,
      engine file untouched on disk, md5-pinned) -> L1's exact program
      lands the host file clean (pre-fix shape reproduced).
  L7  family: BK-40 + BK-41 + BK-39 gates green on this tree (never
      weaken a live guard).

FIXTURE GEOMETRY (probe_bk42_geom_af3e, live _addr_in_box): the GO-2 tile
(5,0,8,8) term is Hilbert-scattered — in-tile contiguous runs are
(160..167), (192..199), (224..231), ...; 168..191 and 200..223 are OUT.
All in-tile staging sits in run (192..199): data word 192, path words
193..199 (6-char paths + NUL fit; longer paths cross the run and trip the
landed BK-39 staging fence — first-draft defect, caught by L4's control
failing with fault_addr=800=word 200).

RED-first at landing time (engine fix stashed): L1..L3 fail with the
measured pre-fix shapes (clean exit, host file lands); L4..L7 pass
(harness live). Fix applied -> 7/7.

What the PASS does NOT prove: VFS-attached FILE_WRITE legs (no VFS device
in this harness), 0x01 WRITE's output window, 0x08/0x09 AUDIO windows,
the WGSL twin (syscall handlers are oracle-Python-only — BK-40
precedent), BK-43's RUN allowlist-smuggle legs beyond the shared
path-decode consult landed here (separate row, own gate).
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
FW_IN_DATA = 192                                    # in-tile data word (run 2)
FW_PATH_ADDR = 193                                  # in-tile path staging

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


# ── L1: FILE_WRITE data window out-of-tile -> refused, NO host file ─────
def test_l1_fw_data_out_of_tile_no_file():
    host = "/tmp/a"
    if os.path.exists(host):
        os.unlink(host)
    prog = (
        _stage(FW_PATH_ADDR, host.encode())
        + [
            "LDI r1 %d" % FW_PATH_ADDR,       # path (in-tile)
            "LDI r2 %d" % OUT_TILE_WORD,      # data window OUT of tile
            "LDI r3 2",                        # len 2
            "SYSCALL r10 3",                   # FILE_WRITE
            "HALT",
        ]
    )
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk42_l1", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    cpu.memory[OUT_TILE_WORD] = ord("F")
    cpu.memory[OUT_TILE_WORD + 1] = ord("K")
    rc = table.wait(pid)
    assert rc == EXIT_FAULT, (rc, cpu.fault_reason)
    assert cpu.faulted, cpu.fault_reason
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4
    assert "syscall_source_fence" in (cpu.fault_reason or ""), cpu.fault_reason
    assert not os.path.exists(host), "host file LANDED — exfil not fenced"
    # the fault is the SYSCALL's, not the staging's: fault_addr pins the
    # first offending DATA word (168*4), and the in-tile path staged fine
    assert int(cpu.memory[FW_PATH_ADDR]) == ord("/"), "path staging corrupted"


# ── L2: LD-fed shape — the out-of-tile LD traps AT THE LD (BK-38 owns
#        that consult); the syscall never fires; no host file ────────────
def test_l2_ld_fed_exfil_traps_at_ld():
    host = "/tmp/b"
    if os.path.exists(host):
        os.unlink(host)
    prog = (
        _stage(FW_PATH_ADDR, host.encode())
        + [
            "LDI r7 %d" % OUT_TILE_WORD,      # out-of-tile source
            "LD r4 r7",                        # GO-2 LD fence consult fires here
            "LDI r1 %d" % FW_PATH_ADDR,
            "LDI r2 %d" % FW_IN_DATA,
            "LDI r3 1",
            "SYSCALL r10 3",
            "HALT",
        ]
    )
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk42_l2", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    cpu.memory[OUT_TILE_WORD] = ord("F")
    rc = table.wait(pid)
    assert rc == EXIT_FAULT, (rc, cpu.fault_reason)
    assert cpu.faulted
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4
    assert not os.path.exists(host), "host file LANDED"


# ── L3: unterminated in-tile path must NOT decode past the tile ─────────
def test_l3_unterminated_path_stops_at_tile():
    """RED today: path staged WITHOUT NUL at words 193..198, word 199 holds
    a non-NUL 'Q' (staged), and out-of-tile words 200/201 hold 'X','Y' with
    a NUL at 202 — _read_path walks past the tile and the host file appears
    at /tmp/a1QXY. Post-fix the path consult refuses (decode crosses the
    tile boundary with no in-tile NUL) and nothing lands."""
    host = "/tmp/c"
    bad = "/tmp/cQXY"         # the pre-fix artifact name
    for p in (host, bad):
        if os.path.exists(p):
            os.unlink(p)
    prog = (
        _stage(FW_PATH_ADDR, host.encode(), term=False)   # NO NUL terminator
        + ["LDI r5 %d" % (FW_PATH_ADDR + len(host)),      # word 199: non-NUL
           "LDI r6 %d" % ord("Q"), "PARALLEL_ST r5 r6 1"]
        + [
            "LDI r1 %d" % FW_PATH_ADDR,
            "LDI r2 %d" % FW_IN_DATA,
            "LDI r3 1",
            "SYSCALL r10 3",
            "HALT",
        ]
    )
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk42_l3", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    # out-of-tile walk targets: 200='X', 201='Y', 202=NUL (simulates the
    # neighbor's RAM the pre-fix decoder crossed into)
    cpu.memory[200] = ord("X")
    cpu.memory[201] = ord("Y")
    cpu.memory[202] = 0
    cpu.memory[FW_IN_DATA] = ord("Z")
    rc = table.wait(pid)
    assert rc == EXIT_FAULT, (rc, cpu.fault_reason)
    assert cpu.faulted, cpu.fault_reason
    assert "path_decode_fence" in (cpu.fault_reason or ""), cpu.fault_reason
    assert not os.path.exists(bad), "decode crossed the tile (pre-fix shape)"
    assert not os.path.exists(host), "unexpected host file"


# ── L4: in-tile controls stay green ──────────────────────────────────────
def test_l4_in_tile_fw_land_and_fr_control():
    # BK-44 migrated the fixture (never weakened): the handlers' host arms
    # now require the realpath under a GLYPH_FS_ALLOW root (BK-44's own
    # change); /tmp is the same scope BK-40's L3 uses. The legs' subjects
    # are the FENCE consults (in-tile windows admitted), not the root
    # check — arming the env keeps the handler landing observable.
    _old = os.environ.get("GLYPH_FS_ALLOW")
    os.environ["GLYPH_FS_ALLOW"] = "/tmp"
    try:
        _l4_body()
    finally:
        if _old is None:
            os.environ.pop("GLYPH_FS_ALLOW", None)
        else:
            os.environ["GLYPH_FS_ALLOW"] = _old


def _l4_body():
    host = "/tmp/d"
    if os.path.exists(host):
        os.unlink(host)
    prog = (
        _stage(FW_PATH_ADDR, host.encode())
        + [
            "LDI r1 %d" % FW_PATH_ADDR,
            "LDI r2 %d" % FW_IN_DATA,        # in-tile data
            "LDI r3 1",
            "SYSCALL r10 3",
            "HALT",
        ]
    )
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk42_l4", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    cpu.memory[FW_IN_DATA] = ord("Z")
    rc = table.wait(pid)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert os.path.exists(host) and Path(host).read_bytes() == b"Z", (
        rc, os.path.exists(host))
    # FILE_READ in-tile path control (0x04 dest also in-tile). Dest 192
    # overlaps the path staging — the handler runs AFTER the path decode,
    # so the overwrite is harmless by construction.
    host2 = "/tmp/e"
    with open(host2, "wb") as f:
        f.write(b"KF")
    prog2 = (
        _stage(FW_PATH_ADDR, host2.encode())
        + [
            "LDI r1 %d" % FW_PATH_ADDR,
            "LDI r2 %d" % FW_IN_DATA,
            "LDI r3 2",
            "SYSCALL r10 4",
            "HALT",
        ]
    )
    img2 = _build(prog2)
    table2 = GlyphProcessTable()
    pid2 = table2.spawn(img2, name="bk42_l4b",
                        tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu2 = table2.tasks[pid2]["cpu"]
    rc2 = table2.wait(pid2)
    assert rc2 == EXIT_OK, (rc2, cpu2.fault_reason)
    assert int(cpu2.memory[FW_IN_DATA]) == ord("K"), int(cpu2.memory[FW_IN_DATA])


# ── L5: ST-out-of-tile trap control (E-K1 baseline intact) ───────────────
def test_l5_st_out_of_tile_control():
    prog = ["LDI r2 %d" % OUT_TILE_WORD, "LDI r3 4660", "ST r2 r3", "HALT"]
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk42_l5", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    rc = table.wait(pid)
    cpu = table.tasks[pid]["cpu"]
    assert rc == EXIT_FAULT, rc
    assert int(getattr(cpu, "fault_addr", 0) or 0) == OUT_TILE_WORD * 4


# ── L6: non-vacuity — neuter the consults, pre-fix shape returns ────────
def test_l6_non_vacuity():
    # BK-44 migrated (never weakened): the neutered consults reproduce the
    # PRE-BK-42 shape, but the landing still rides the BK-44 host-arm root
    # check — /tmp armed so the exfil file can land (the shape under test
    # is the fence consult, not the root check).
    _old = os.environ.get("GLYPH_FS_ALLOW")
    os.environ["GLYPH_FS_ALLOW"] = "/tmp"
    try:
        _l6_body()
    finally:
        if _old is None:
            os.environ.pop("GLYPH_FS_ALLOW", None)
        else:
            os.environ["GLYPH_FS_ALLOW"] = _old


def _l6_body():
    host = "/tmp/f"
    if os.path.exists(host):
        os.unlink(host)
    md5_before = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()
    prog = (
        _stage(FW_PATH_ADDR, host.encode())
        + [
            "LDI r1 %d" % FW_PATH_ADDR,
            "LDI r2 %d" % OUT_TILE_WORD,
            "LDI r3 2",
            "SYSCALL r10 3",
            "HALT",
        ]
    )
    img = _build(prog)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk42_l6", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    # instance-attribute shadowing, engine file untouched on disk (BK-40
    # L7 style): both new consults admit everything -> pre-fix exfil.
    cpu._bk42_source_fault = lambda *a, **k: None
    cpu._bk42_path_fault = lambda *a, **k: None
    cpu.memory[OUT_TILE_WORD] = ord("F")
    cpu.memory[OUT_TILE_WORD + 1] = ord("K")
    rc = table.wait(pid)
    md5_after = hashlib.md5(_ENGINE_PATH.read_bytes()).hexdigest()
    assert md5_before == md5_after == _ENGINE_MD5, (md5_before, md5_after)
    assert rc == EXIT_OK, (rc, cpu.fault_reason)
    assert os.path.exists(host) and Path(host).read_bytes() == b"FK", (
        "pre-fix exfil shape NOT reproduced — non-vacuity leg vacuous")
    if os.path.exists(host):
        os.unlink(host)


# ── L7: family — BK-40 + BK-41 + BK-39 gates green on this tree ─────────
def test_l7_family():
    for gate in ("tests/test_bk40_syscall_fence.py",
                 "tests/test_bk41_ksys_fence.py",
                 "tests/test_bk39_write_fence.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert p.returncode == 0, (gate, p.stdout[-2000:])
