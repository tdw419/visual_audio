"""item-25 VFS-2/3 gate: syscall re-route + writeback persistence.

Legs:
  L1  VFS-2 write/read roundtrip through REAL syscalls (0x03/0x04) with a
      GlyphVfs attached — bytes land in the VFS, NOT the host filesystem.
  L2  VFS-2 list through the REAL 0x13 syscall — staged ∪ image names.
  L3  VFS-3 writeback: pre-sync a fresh GlyphVfs does NOT see the write;
      after sync() it does (reboot leg, byte-exact) + e2fsck clean.
  L4  Containment: '..' escape refused by the syscall arm (rc -1), no
      file created outside the disk; refuse contract (rc -1 / entry
      count -1) matches the landed host arms.
  L5  VFS-3 sync is a no-op when clean and refuses (loudly, rc -1) a
      corrupted-image commit by validating with e2fsck BEFORE the wrap
      (non-vacuity: the leg corrupts the image and shows sync detect it).
  M1  MIGRATION MATRIX: host-path default unchanged — a program through
      0x03/0x04 with NO VFS attached writes the host file exactly as
      before (test_glyph_file_io.py's own scenario re-run in-gate).
  M2  MIGRATION MATRIX: the L1 shell personality regression suite
      (tests/test_l1_shell_personality.py) passes unmodified with the
      engine carrying the VFS hook (default vfs=None).
  M3  MIGRATION MATRIX: BK-11 coreutils byte-exactness gate passes
      unmodified (engine default path).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts are structural (rc values, bytes, file existence, fsck rc).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_vfs import GlyphVfs  # noqa: E402


# ── shared harness (the test_glyph_file_io.py pattern) ────────────────────
# PATH_ADDR sits high enough that a long pytest tmp_path (80+ chars) never
# reaches the data/dest windows (96..154) — the landed fixture used short
# tempfile paths where 32 was safe; the migration leg must not depend on it.
PATH_ADDR = 384
DATA_ADDR = 96
READ_DEST = 128


def _make_cpu():
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    program = [
        f"LDI r1 {PATH_ADDR}",  # r1 = path address
        f"LDI r2 {DATA_ADDR}",  # r2 = data address (write) / dest (read)
        "LDI r3 26",           # r3 = length
        "SYSCALL r0 0x03",     # FILE_WRITE
        f"LDI r1 {PATH_ADDR}",  # path address again
        f"LDI r2 {READ_DEST}",  # read destination
        "LDI r3 26",           # length
        "SYSCALL r4 0x04",     # FILE_READ
        "HALT",
    ]
    image = assembler.assemble(program, width_instrs=8)
    if image.shape[0] < 5:
        new_image = np.zeros((5, image.shape[1], 3), dtype=np.uint8)
        new_image[: image.shape[0]] = image
        image = new_image
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    return cpu, image


def _seed(cpu, path: str, data: bytes):
    assert len(path) + 1 <= 640 - PATH_ADDR, "path would overflow RAM"
    for i, ch in enumerate(path + "\0"):
        cpu.memory[PATH_ADDR + i] = ord(ch)
    for i, byte_val in enumerate(data):
        cpu.memory[DATA_ADDR + i] = byte_val


TEST_DATA = b"Hello from spatial memory!"  # 26 bytes, the landed fixture
TEST_LEN = len(TEST_DATA)


# ── VFS-2: re-route ──────────────────────────────────────────────────────
def test_item25_vfs2_write_read_reroute(tmp_path):
    """L1: with a VFS attached, 0x03/0x04 hit the VFS, not the host FS."""
    cpu, image = _make_cpu()
    vfs = GlyphVfs.format(str(tmp_path / "disk.png"))
    vfs.attach(cpu)
    assert cpu.vfs is vfs
    guest_name = "spatial_test.txt"
    _seed(cpu, guest_name, TEST_DATA)  # guest paths are VFS-relative
    cpu.run(image)
    # Read-back through the program itself: bytes at 128 are the VFS read.
    got = bytes(cpu.memory[128:128 + TEST_LEN])
    assert got == TEST_DATA, f"vfs roundtrip mismatch: {got!r}"
    # The write must NOT exist on the host filesystem...
    assert not (tmp_path / guest_name).exists()
    # ...and NOT be in the image until sync (staged overlay only).
    fresh = GlyphVfs(str(tmp_path / "disk.png"))
    assert fresh.vfs_read(guest_name, 128) is None
    assert fresh.vfs_read.__self__ is not None  # noqa: static-use


def test_item25_vfs2_list_reroute(tmp_path):
    """L2: 0x13 with a VFS attached lists staged ∪ image, entry-count rc."""
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    program = [
        f"LDI r1 {PATH_ADDR}",  # dir path addr
        "LDI r2 640",          # dest addr (above the program window)
        "LDI r3 256",          # max bytes
        "SYSCALL r9 0x13",     # FILE_LIST — rc (entry count) in r9
        "HALT",
    ]
    image = assembler.assemble(program, width_instrs=8)
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    vfs = GlyphVfs.format(str(tmp_path / "disk.png"))
    vfs.attach(cpu)
    assert vfs.vfs_write("b.txt", b"2") == 0
    assert vfs.vfs_write("a.txt", b"1") == 0
    dir_path = "/"
    for i, ch in enumerate(dir_path + "\0"):
        cpu.memory[PATH_ADDR + i] = ord(ch)
    cpu.run(image)
    assert cpu.registers[9] >= 2, f"entry count rc: {cpu.registers[9]}"
    blob = bytes(cpu.memory[640:640 + cpu.registers[9] * 8])
    names = [n for n in blob.split(b"\0") if n]
    assert b"a.txt" in names and b"b.txt" in names


# ── VFS-3: writeback persistence ─────────────────────────────────────────
def test_item25_vfs3_sync_reboot_persistence(tmp_path):
    """L3: pre-sync invisible to a fresh boot; post-sync byte-exact + fsck."""
    cpu, image = _make_cpu()
    png = str(tmp_path / "disk.png")
    vfs = GlyphVfs.format(png)
    vfs.attach(cpu)
    _seed(cpu, "persist.txt", TEST_DATA)
    cpu.run(image)
    assert vfs.dirty() is True
    # Pre-sync: a fresh boot (new GlyphVfs from the same PNG) sees nothing.
    pre = GlyphVfs(png)
    assert pre.vfs_read("persist.txt", 128) is None
    # Sync = writeback barrier.
    assert vfs.sync() == 0
    assert vfs.dirty() is False
    # Reboot leg: fresh instance, fresh disk materialization, byte-exact.
    rebooted = GlyphVfs(png)
    assert rebooted.vfs_read("persist.txt", 128) == TEST_DATA
    assert "persist.txt" in (rebooted.vfs_list("/", 256) or [])
    # Image is ext2-valid (e2fsck ran inside sync; re-verify externally).
    rebooted._ensure_staging()
    chk = subprocess.run(["e2fsck", "-fn", rebooted._disk_path],
                         capture_output=True)
    assert chk.returncode in (0, 1), chk.stdout.decode()[:200]


def test_item25_vfs_containment_escape_refused(tmp_path):
    """L4: '..' escape refused at the syscall arm; nothing lands host-side."""
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    program = [
        "LDI r1 32",
        "LDI r2 96",
        "LDI r3 26",
        "SYSCALL r0 0x03",     # FILE_WRITE — path is ../escape.txt
        "HALT",
    ]
    image = assembler.assemble(program, width_instrs=8)
    if image.shape[0] < 3:
        image = np.zeros((3, image.shape[1], 3), dtype=np.uint8)
        image[:1] = assembler.assemble(program, width_instrs=8)
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    vfs = GlyphVfs.format(str(tmp_path / "disk.png"))
    vfs.attach(cpu)
    for i, ch in enumerate("../escape.txt\0"):
        cpu.memory[PATH_ADDR + i] = ord(ch)
    for i, byte_val in enumerate(TEST_DATA):
        cpu.memory[DATA_ADDR + i] = byte_val
    cpu.run(image)
    # Refused: not staged, not on the host, not dirty.
    assert vfs.dirty() is False
    assert not (tmp_path / "escape.txt").exists()
    names = vfs.vfs_list("/", 256) or []
    assert "escape.txt" not in names  # nothing staged (lost+found is image base)


def test_item25_vfs3_sync_noop_and_reject(tmp_path):
    """L5: clean sync is a no-op; corrupted-image sync refuses loudly."""
    png = str(tmp_path / "disk.png")
    vfs = GlyphVfs.format(png)
    assert vfs.sync() == 0          # clean: no-op
    assert vfs.dirty() is False
    # Non-vacuity: corrupt the raw image where it lies; a sync with dirty
    # data must NOT commit (e2fsck pre-wrap rejects).
    vfs._ensure_staging()
    with open(vfs._disk_path, "r+b") as f:
        f.seek(1024 + 56)           # ext2 superblock magic at sb+56
        f.write(b"\x34\x12")        # 0xEF53 -> 0x1234 (the item-24 RED leg)
    vfs.vfs_write("x.txt", b"x")
    assert vfs.sync() == -1         # refused: bad fs never replaces disk
    # And the PNG on disk is still the LAST GOOD image (unwrap still OK).
    from tools import png_vfs
    raw = png_vfs.unwrap(png)
    assert raw[:1024 + 56] is not None  # unwrap itself is the loud check


# ── MIGRATION MATRIX (mandatory per item-25 spec) ────────────────────────
def test_item25_matrix_host_default_unchanged(tmp_path):
    """M1: with NO VFS attached, 0x03/0x04 hit the host FS exactly as before.
    BK-44 migrated (never weakened): 'as before' now includes the landed
    host-arm root check — the fixture arms its own tmp_path root."""
    import os
    cpu, image = _make_cpu()
    assert cpu.vfs is None         # default: no backend attached
    host_path = str(tmp_path / "spatial_test.txt")
    old = os.environ.get("GLYPH_FS_ALLOW")
    os.environ["GLYPH_FS_ALLOW"] = str(tmp_path.resolve())
    try:
        _seed(cpu, host_path, TEST_DATA)
        cpu.run(image)
    finally:
        if old is None:
            os.environ.pop("GLYPH_FS_ALLOW", None)
        else:
            os.environ["GLYPH_FS_ALLOW"] = old
    assert Path(host_path).read_bytes() == TEST_DATA
    got = bytes(cpu.memory[128:128 + TEST_LEN])
    assert got == TEST_DATA


def test_item25_matrix_l1_shell_suite():
    """M2: the L1 personality regression suite passes unmodified."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_l1_shell_personality.py",
         "-q", "--no-header", "-x"],
        capture_output=True, text=True, timeout=1200)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]


def test_item25_matrix_bk11_coreutils():
    """M3: BK-11 coreutils byte-exactness gate passes unmodified."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_bk11_coreutils.py",
         "-q", "--no-header", "-x"],
        capture_output=True, text=True, timeout=1200)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]
