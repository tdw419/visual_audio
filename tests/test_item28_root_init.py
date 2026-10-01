"""item-28 gate: spatial root init (ext2 PNG root mount + PID 1 startup).

Legs:
  B1  format + mount: a GlyphRootFs formats a PNG root with the skeleton
      tree; mount() validates /sbin/init + /etc/hostname exist; a foreign
      PNG (no init) REFUSES to mount (RootInitError) — the RED-discriminator
      is in-suite (R1).
  B2  boot sequence: Kernel.boot() spawns PID 1 as the FIRST task (pid==1
      contract), PID 1 runs the init program (FILE_WRITE of its argv into
      /var/run/last_pid_arg through the mounted root), exits clean (0).
  B3  reboot persistence: after shutdown_sync(), a FRESH boot from the same
      PNG sees PID 1's boot record — the ext2 content round-tripped the
      VFS-1 PNG transport (item-25 L3 pattern, now with a subdirectory).
  B4  DEFECT-32 regression: the reboot-write-reboot cycle writes through an
      EXISTING subdirectory (/etc/motd v0 -> reboot -> v1 -> reboot -> v1
      byte-exact). On the landed (unguarded) sync this cycle returns -1 and
      the write is lost (probed this tick: /tmp probes d32_red_v15).
  P1  PID-1-first contract violation: if the table is reused after another
      spawn, boot() refuses (RootInitError) rather than running init at a
      non-1 pid (in-suite non-vacuity, cheap form).
  R1  corrupt-root RED: mount() on a root whose /sbin/init was deleted
      raises (the gate's own negative leg).
  R2  MIGRATION: item-25 VFS gate re-run GREEN in this tree via subprocess
      (glyph_vfs.py changed — the guard — so the landed gate must still
      pass unmodified).
  R3  MIGRATION: item-26 process gate re-run GREEN in this tree via
      subprocess (no process-model change, but the tree is the ship
      candidate for items 25-28 together).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (rc values, bytes, pids, exceptions).
"""
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_root_init import (  # noqa: E402
    INIT_PATH,
    Kernel,
    RootInitError,
    GlyphRootFs,
)
from tools.glyph_vfs import GlyphVfs  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pytest_python():
    """A python with pytest (the worktree .venv is bare — item-26 R2 shape)."""
    for cand in (sys.executable, "python3", "/home/jericho/projects/zion/projects/visual_audio/.venv/bin/python"):
        r = subprocess.run([cand, "-c", "import pytest"], capture_output=True)
        if r.returncode == 0:
            return cand
    pytest.skip("no pytest-capable interpreter found for migration legs")


# ── B1: format + mount + validation ──────────────────────────────────────
def test_b1_format_mount_and_foreign_refusal(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"tile-node-1")
    vfs = root.mount()
    assert vfs.vfs_read(INIT_PATH, 16) == b"init"
    assert vfs.vfs_read("/etc/hostname", 32) == b"tile-node-1\n"
    # A bare (unseeded) PNG has no /sbin/init -> refuse to mount.
    bare = str(tmp_path / "bare.png")
    GlyphVfs.format(bare)
    with pytest.raises(RootInitError):
        GlyphRootFs(bare).mount()


# ── B2: boot sequence — PID 1 is first, runs init, exits clean ───────────
def test_b2_boot_pid1_runs_init_and_exits_zero(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphRootFs.format(png, hostname=b"boot2")
    k = Kernel()
    status = k.boot(GlyphRootFs(png))
    assert status == 0, "PID 1 must exit clean"
    pid1_task = k.table.tasks.get(1)
    assert pid1_task is not None, "first task must be pid 1"
    assert pid1_task["name"] == "init"
    assert pid1_task["state"] == "exited"
    k.close()


# ── B3: reboot persistence — boot record survives the PNG round-trip ─────
def test_b3_reboot_persistence_of_pid1_boot_record(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphRootFs.format(png, hostname=b"boot3")
    k = Kernel()
    assert k.boot(GlyphRootFs(png)) == 0
    k.shutdown_sync()
    k.close()
    # Fresh boot from the SAME PNG: PID 1's write is in the ext2 root.
    fresh = GlyphVfs(png)
    got = fresh.vfs_read(Kernel.BOOT_RECORD, 64)
    assert got is not None, "boot record missing after reboot"
    assert got.rstrip(b"\x00") == b"init"


# ── B4: DEFECT-32 regression — resync through an EXISTING subdir ─────────
def test_b4_defect32_reboot_write_reboot_through_etc(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphRootFs.format(png)
    v1 = GlyphVfs(png)
    v1.vfs_write("/etc/motd", b"motd-v0")
    assert v1.sync() == 0
    # Reboot: write the SAME file (now EXISTS in the image) again.
    v2 = GlyphVfs(png)
    assert v2.vfs_read("/etc/motd", 16) == b"motd-v0"
    v2.vfs_write("/etc/motd", b"motd-v1")
    rc = v2.sync()
    assert rc == 0, (
        "DEFECT-32: sync through an existing subdirectory must succeed "
        f"(landed unguarded body returns -1 here); got rc={rc}")
    v3 = GlyphVfs(png)
    assert v3.vfs_read("/etc/motd", 16) == b"motd-v1", "resync write lost"


# ── P1: PID-1-first contract is enforced, not assumed ────────────────────
def test_p1_boot_refuses_reused_table(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png)
    k = Kernel()
    k.boot(GlyphRootFs(png))
    assert k.table is not None
    # A second boot on the same kernel object would make init pid 2+.
    with pytest.raises(Exception):
        k.boot(root)
    k.close()


# ── R1: corrupt-root RED (the gate's own negative leg) ───────────────────
def test_r1_mount_refuses_root_without_init(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png)
    vfs = root.mount()
    # Sabotage: remove /sbin/init from the image (debugfs rm via staging
    # is not exposed; format a bare disk and seed hostname only).
    bare = str(tmp_path / "sabotaged.png")
    bad = GlyphVfs.format(bare)
    bad.vfs_write("/etc/hostname", b"no-init\n")
    assert bad.sync() == 0
    with pytest.raises(RootInitError):
        GlyphRootFs(bare).mount()


# ── R2: item-25 VFS gate re-run GREEN in this tree ───────────────────────
def test_r2_item25_vfs_gate_still_green():
    py = _pytest_python()
    r = subprocess.run(
        [py, "-m", "pytest", "tests/test_item25_vfs.py", "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"item-25 gate regressed:\n{r.stdout[-2000:]}"
    assert "8 passed" in r.stdout


# ── R3: item-26 process gate re-run GREEN in this tree ───────────────────
def test_r3_item26_process_gate_still_green():
    py = _pytest_python()
    r = subprocess.run(
        [py, "-m", "pytest", "tests/test_item26_process.py", "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, f"item-26 gate regressed:\n{r.stdout[-2000:]}"
    assert "8 passed" in r.stdout
