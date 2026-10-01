#!/usr/bin/env python3
"""BK-45 gate — VFS-dest fence guard (step 7 / closing row of the
sequenced fence commit; row: systems/GLYPH_BACKLOG.md BK-45).

DEFECT (measured at HEAD 4b0bb0c1, probe
.builder_queue/probe_vfs_fence_af3e.py, receipt
.builder_queue/RESEARCH_vfs_twin_fence.md, results md5
c1ac611a712160654dfddd7ed4be27ee): with a GlyphVfs attached, the
0x04 FILE_READ and 0x13 FILE_LIST VFS-reroute dest loops copied handler
output into guest RAM with bounds checks only — an OUT-of-tile dest
landed clean from a tile-confined USER task (leg 8: rc 2, 'VW' at
168/169; leg 9: rc 4, listing bytes at 168..), while plain ST to the
same word trapped E-K1. BK-40's fence-blind dest class, VFS route.

FIX POSTURE (measured on the current tree, NOT assumed): BK-40's
landed dispatch-site consult (glyph_isa_v2.py SYSCALL arm, dest_specs
0x04/0x13 + _bk42_path_fault for the path arg) runs BEFORE
_handle_syscall regardless of VFS attachment, so the VFS reroute arms
are already covered by the same consult — the VFS layer inherits the
fence at the dispatch site, no new engine consult site needed. This
gate LANDS THE DEVICE LEGS the row names and BK-40 never ran: every
leg spawns a real GlyphVfs (GlyphVfs.format on a tmp_path PNG,
vfs_shared=True) so the verdicts exercise the VFS-reroute arms
themselves, not the host twins.

Legs:
  L1  0x04 VFS-staged read, dest out-of-tile -> fault, nothing lands
      (RED at 4b0bb0c1: 'VW' landed). VFS layer live on both sides:
      the in-tile control (L3) round-trips through vfs_write/vfs_read.
  L2  0x13 VFS listing, dest out-of-tile -> fault, nothing lands
      (RED at 4b0bb0c1: listing bytes landed).
  L3  in-tile dest controls stay green THROUGH THE VFS (write staged,
      read back, listed) — the fence must not brick lawful VFS data
      handlers (never over-confine).
  L4  '..' escape refusals stay green with the fence live (rc -1 via
      _guest_rel) — the VFS path containment SURVIVES the dest fence
      (never weaken a live guard).
  L5  host-absence control: a host-shaped path '/tmp/bk45_host' via
      0x03 with the VFS attached stages INSIDE the image; the host
      file must not exist (attachment state decides FS blast radius).
  L6  non-vacuity: the BK-40 dest consult instance-shadowed -> L1's
      exact shape LANDS 'VW' out-of-tile clean again (the landed
      consult is the refusal, not the VFS layer); engine file
      md5-pinned before/after.
  L7  family: BK-40 + BK-42 + item-25 + item-29 gates green on this
      tree (never weaken a live guard).

Honesty: structural asserts only (rc, fault_addr, bytes, host-FS
state) — numbers structural, rule-1 floors do not attach.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, OpcodeMapV2, W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402
from tools.glyph_vfs import GlyphVfs  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 168: first word outside
#   (rows 5-12 x cols 0-7). Same geometry disclosure as BK-40: 160+64=224
#   is row 7 col 0 = INSIDE; the probe's proven-safe staging run.
STAGE_WORD = IN_TILE_WORD                           # path staging at 160
IN_DEST = IN_TILE_WORD + 32                         # 192: row 6 col 0, in-tile
ENGINE_MD5 = hashlib.md5(
    (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()


def _worker_disk(tmp_path):
    """One SHARED staging disk per pytest-xdist worker (per-worker file
    under tmp_path's session sibling — tmp_path itself is per-TEST, and
    the first draft built a fresh GlyphVfs per syscall, so a leg's
    staged write was invisible to its own later read-back: 'file not
    found', caught by L3's roundtrip leg). Gated by the BK45_DISK env
    var so the family subprocess (L7) and interactive runs don't share
    it accidentally."""
    root = Path(os.environ.get("BK45_DISK_ROOT",
                               "/tmp/bk45_gate_" + os.environ.get(
                                   "PYTEST_XDIST_WORKER", "main")))
    root.mkdir(parents=True, exist_ok=True)
    png = root / "disk.png"
    if not png.exists():
        GlyphVfs.format(str(png), size_bytes=1 << 20, blocksize=1024)
    return str(png)


# THE STAGING OVERLAY LIVES ON THE GlyphVfs OBJECT (its per-object
# tempdir), NOT on the PNG file: trace15 proved two GlyphVfs(disk.png)
# objects in one process see DIFFERENT empty staging roots, so a fresh
# GlyphVfs per syscall call made every leg's staged write invisible to
# its own later read-back. Cache the OBJECT per worker — one shared
# overlay per pytest run, the process model the legs assert against.
_VFS_CACHE: dict[str, GlyphVfs] = {}


def _worker_vfs() -> GlyphVfs:
    key = os.environ.get("PYTEST_XDIST_WORKER", "main")
    if key not in _VFS_CACHE:
        _VFS_CACHE[key] = GlyphVfs(_worker_disk(None))
    return _VFS_CACHE[key]


def _build(lines):
    return GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)


def _stage_path(path_bytes, sysnum, dest, count):
    """Stage an in-tile NUL-terminated path at word 160 (PARALLEL_ST
    staging, <=9-byte paths — the probe's proven-safe geometry: a longer
    path's write-through mirror self-overwrites the program image,
    receipted in RESEARCH_vfs_twin_fence.md), then issue the syscall
    with r1=path_addr, r2=dest, r3=count. Park rc at word 198 (in-tile)
    so the syscall's OWN rc is asserted, not just the exit status."""
    assert path_bytes.endswith(b"\x00") and len(path_bytes) <= 16
    out = []
    for i, b in enumerate(path_bytes):
        out += ["LDI r5 %d" % (STAGE_WORD + i), "LDI r6 %d" % b,
                "PARALLEL_ST r5 r6 1"]
    out += ["LDI r1 %d" % STAGE_WORD,
            "LDI r2 %d" % dest,
            "LDI r3 %d" % count,
            "SYSCALL r10 %d" % sysnum,
            "LDI r2 198",
            "ST r2 r10",
            "HALT"]
    return out


def _run_vfs_case(prog, seed=None, neuter=False):
    """Spawn a tile-confined USER task with a REAL attached GlyphVfs and
    run the program. The VFS staging DISK is PER-WORKER (one shared
    overlay per pytest run): a leg is a SEQUENCE of syscalls against the
    same staging root, matching the process model — a staged write must
    be visible to that leg's own later read-back."""
    img = _build(prog)
    vfs = _worker_vfs()
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk45",
                      tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W),
                      vfs=vfs, vfs_shared=True)
    cpu = table.tasks[pid]["cpu"]
    if neuter:
        # Non-vacuity instrument (BK-40 L7 style): the dest consult
        # admits everything -> the pre-fix VFS-dest behavior must
        # reappear. Instance shadow; engine file untouched on disk.
        cpu._bk40_dest_fault = lambda dest, length, kind: None
    for addr, val in (seed or {}).items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    fields = {
        "rc": rc,
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "reason": (cpu.fault_reason or ""),
        "syscall_rc": int(cpu.memory[198]) & 0xFFFFFFFF,
        "out_bytes": bytes(cpu.memory[OUT_TILE_WORD + i] & 0xFF
                           for i in range(4)),
        "in_bytes": bytes(cpu.memory[IN_DEST + i] & 0xFF
                          for i in range(8)),
        "mode_super": int(cpu.mode) == 0,
        "vfs": vfs,
    }
    return fields


# ── L1: 0x04 VFS read, dest out-of-tile -> refused ──────────────────────
def test_l1_vfs_read_dest_out_of_tile_traps():
    """RED at 4b0bb0c1: rc 2, 'VW' landed at 168/169 clean."""
    prog = _stage_path(b"q1.txt\x00", 4, OUT_TILE_WORD, 64)
    # stage the file INTO the VFS first (host-side staging write through
    # the same GlyphVfs API the syscall arm uses — L3 proves the roundtrip)
    r_seed = {OUT_TILE_WORD: 0, OUT_TILE_WORD + 1: 0}
    # pre-stage via a first run that writes q1.txt through the VFS arm
    wprog = _stage_path(b"q1.txt\x00", 3, IN_DEST, 2)
    w = _run_vfs_case(wprog,
                      seed={IN_DEST: 0x56, IN_DEST + 1: 0x57})   # 'V','W'
    assert w["rc"] == EXIT_OK and w["syscall_rc"] == 0, w
    r = _run_vfs_case(prog, seed=r_seed)
    assert r["rc"] == EXIT_FAULT, r
    assert r["faulted"], r
    assert r["fault_addr"] == OUT_TILE_WORD * 4, r       # 672 = 168*4
    assert "syscall_dest_fence" in r["reason"], r
    assert r["syscall_rc"] == 0, r                        # handler never ran
    assert r["out_bytes"][:2] == b"\x00\x00", r           # nothing landed
    assert r["mode_super"], r                             # E-K1 tail


# ── L2: 0x13 VFS listing, dest out-of-tile -> refused ───────────────────
def test_l2_vfs_list_dest_out_of_tile_traps():
    """RED at 4b0bb0c1: rc 4, listing bytes landed at 168.. clean."""
    prog = _stage_path(b"/\x00", 0x13, OUT_TILE_WORD, 64)
    r = _run_vfs_case(prog,
                      seed={OUT_TILE_WORD: 0, OUT_TILE_WORD + 1: 0})
    assert r["rc"] == EXIT_FAULT, r
    assert r["faulted"], r
    assert r["fault_addr"] == OUT_TILE_WORD * 4, r
    assert "syscall_dest_fence" in r["reason"], r
    assert r["syscall_rc"] == 0, r
    assert r["out_bytes"] == b"\x00\x00\x00\x00", r       # nothing landed


# ── L3: in-tile VFS controls stay green (write/read/list roundtrip) ─────
def test_l3_vfs_in_tile_controls_land():
    # 0x03 staged write, in-tile dest
    w = _run_vfs_case(_stage_path(b"ctl.txt\x00", 3, IN_DEST, 2),
                      seed={IN_DEST: 0x56, IN_DEST + 1: 0x57})
    assert w["rc"] == EXIT_OK and w["syscall_rc"] == 0, w
    assert not w["faulted"], w
    # 0x04 staged read back, in-tile dest
    r = _run_vfs_case(_stage_path(b"ctl.txt\x00", 4, IN_DEST + 4, 2),
                      seed={IN_DEST + 4: 0})
    assert r["rc"] == EXIT_OK and r["syscall_rc"] == 2, r
    assert r["in_bytes"][4:6] == b"VW", r
    # 0x13 listing, in-tile dest -> entry count >= 1. DECLARED window
    # posture (BK-40): the consult judges the DECLARED count (r3), and
    # the tile's in-tile runs are 8 words every 32 (rows 5-12 x cols
    # 0-7) — r3=64 declared words 192..255 crosses word 200 ((6,8), OUT)
    # and the landed consult correctly refused it (caught by this leg's
    # own run: fault 800 = word 200). Lawful in-tile listing declares
    # max 8: words 192..199, one full run.
    lst = _run_vfs_case(_stage_path(b"/\x00", 0x13, IN_DEST, 8),
                        seed={IN_DEST: 0})
    assert lst["rc"] == EXIT_OK, lst
    assert 1 <= lst["syscall_rc"] <= 0x7FFFFFFF, lst      # entry count
    assert not lst["faulted"], lst


# ── L4: '..' escape refusals stay green with the fence live ─────────────
def test_l4_vfs_path_refusals_survive():
    """Never weaken a live guard: _guest_rel's refusals must still be
    rc -1 (not converted into fence faults — the refusal is the VFS
    layer's, handler-side, faulted=False)."""
    w = _run_vfs_case(_stage_path(b"../../\x00", 3, IN_DEST, 2),
                      seed={IN_DEST: 0x58, IN_DEST + 1: 0x59})
    assert w["rc"] == EXIT_OK, w                 # clean exit, refusal in rc
    assert w["syscall_rc"] == 0xFFFFFFFF, w      # -1 from _guest_rel
    assert not w["faulted"], w
    d = _run_vfs_case(_stage_path(b"..\x00", 0x13, IN_DEST, 8),
                      seed={IN_DEST: 0})
    assert d["rc"] == EXIT_OK, d
    assert d["syscall_rc"] == 0xFFFFFFFF, d
    assert not d["faulted"], d


# ── L5: host-absence control (VFS-attached -> no host FS touch) ─────────
def test_l5_host_shaped_path_stays_inside_image():
    # 7-char path + NUL = 8 staging words 160..167, ALL in-tile (a longer
    # host-shaped path's staging run would cross word 168 and the landed
    # BK-39 fence would trap the STAGING PARALLEL_ST — harness shape, not
    # a containment verdict; the BK-42 landing receipted the same shape).
    prog = _stage_path(b"/bk45h\x00", 3, IN_DEST, 2)
    r = _run_vfs_case(prog, seed={IN_DEST: 0x5A, IN_DEST + 1: 0x5B})
    assert r["rc"] == EXIT_OK and r["syscall_rc"] == 0, r
    assert not os.path.exists("/tmp/bk45h"), r   # staged INSIDE the image
    assert r["vfs"].dirty(), r                   # ...in the VFS overlay


# ── L6: non-vacuity — neuter the consult, RED shape returns ─────────────
def test_l6_non_vacuity():
    """The BK-40 dest consult instance-shadowed -> L1's exact shape must
    land 'VW' out-of-tile CLEAN again (rc 2 syscall, EXIT_OK) — proving
    the landed consult is what refuses the VFS arms, not the VFS layer.
    Engine file md5-pinned before/after."""
    md5_before = hashlib.md5(
        (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()
    w = _run_vfs_case(_stage_path(b"nv.txt\x00", 3, IN_DEST, 2),
                      seed={IN_DEST: 0x56, IN_DEST + 1: 0x57})
    assert w["rc"] == EXIT_OK and w["syscall_rc"] == 0, w
    prog = _stage_path(b"nv.txt\x00", 4, OUT_TILE_WORD, 64)
    r = _run_vfs_case(prog,
                      seed={OUT_TILE_WORD: 0, OUT_TILE_WORD + 1: 0},
                      neuter=True)
    md5_after = hashlib.md5(
        (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()
    assert md5_before == md5_after == ENGINE_MD5, (md5_before, md5_after)
    assert r["rc"] == EXIT_OK, r                  # the pre-fix shape...
    assert r["syscall_rc"] == 2, r                # ...rc 2 (2 bytes read)
    assert r["out_bytes"][:2] == b"VW", r         # ...'VW' LANDED out-of-tile
    assert not r["faulted"], r


# ── L7: family — BK-40 + BK-42 + item-25 + item-29 gates green ──────────
def test_l7_family():
    for gate in ("tests/test_bk40_syscall_fence.py",
                 "tests/test_bk42_fw_exfil_fence.py",
                 "tests/test_item25_vfs.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert p.returncode == 0, (gate, p.stdout[-2000:])
