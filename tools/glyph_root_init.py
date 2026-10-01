"""glyph_root_init.py — item-28: spatial root init (ext2 PNG root mount +
PID 1 startup sequence).

Layer contract (items 25-27 landed the foundation):

  - VFS-1 (tools/png_vfs.py): ext2 content wrapped in a PNG (PVFSIMG1
    transport, frozen in docs/DRIVER_ABI_v1.md BLOCK channel).
  - VFS-2/3 (tools/glyph_vfs.py): GlyphVfs attaches to an engine; FILE
    syscalls re-route to the ext2 image; sync() writes back and re-wraps.
  - item-26 (tools/glyph_process.py): GlyphProcessTable spawns tasks as
    fresh GlyphCPUv2 engines; PID 1 is the first pid the table hands out.

item-28 assembles these into a BOOT:

  - GlyphRootFs: an ext2 root image in the PNG transport, seeded with a
    deterministic skeleton tree (/etc/hostname, /sbin/init, /var/...).
    `mount()` validates the root (has /sbin/init) and returns the VFS.
  - Kernel: mounts the root PNG, then runs the boot sequence: PID 1 is
    spawned FIRST via the process table (the init program = the task
    named by /sbin/init's argv line), the root VFS attached shared.
    boot() returns a BootResult; reboot() persists PID 1's writes via
    VFS-3 sync and boots a FRESH GlyphRootFs from the same PNG — the
    persistence proof is the reboot leg of the gate.

NO new syscall numbers, NO engine changes (boot is a host-side sequence
over landed abstractions — Phase-2 doctrine; the WGSL twin is out of the
shader threat model for the same reason as item-27).
"""
from __future__ import annotations

import os
import tempfile

import numpy as np

from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
from tools.glyph_process import GlyphProcessTable
from tools.glyph_vfs import GlyphVfs

INIT_PATH = "/sbin/init"
HOSTNAME_PATH = "/etc/hostname"


class RootInitError(Exception):
    """Raised on boot misuse — loud, never silent."""


class GlyphRootFs:
    """An ext2 root image in the VFS-1 PNG transport, with boot validation."""

    def __init__(self, png_path: str):
        self.png_path = str(png_path)
        self._vfs: GlyphVfs | None = None

    @classmethod
    def format(cls, png_path: str, hostname: bytes = b"glyphos",
               size_bytes: int = 1 << 20) -> "GlyphRootFs":
        """Create and seed a fresh root: the skeleton tree PID 1 expects."""
        root = cls(png_path)
        vfs = GlyphVfs.format(png_path, size_bytes=size_bytes)
        vfs.vfs_write(HOSTNAME_PATH, hostname + b"\n")
        # /sbin/init: a task image path reference (the boot argv line),
        # stored as a file the boot sequence reads.
        vfs.vfs_write(INIT_PATH, b"init")
        vfs.vfs_write("/var/run/utmp", b"")
        rc = vfs.sync()
        if rc != 0:
            raise RootInitError(f"root format sync failed rc={rc}")
        root._vfs = vfs
        return root

    def mount(self) -> GlyphVfs:
        """Load the root PNG and validate it is bootable (has /sbin/init).

        Raises RootInitError on a missing init — a corrupt or foreign root
        refuses to mount (loud, never silent).
        """
        vfs = GlyphVfs(self.png_path)
        if vfs.vfs_read(INIT_PATH, 64) is None:
            raise RootInitError(f"root {self.png_path} has no {INIT_PATH}")
        if vfs.vfs_read(HOSTNAME_PATH, 64) is None:
            raise RootInitError(f"root {self.png_path} has no {HOSTNAME_PATH}")
        self._vfs = vfs
        return vfs

    # Convenience re-exports (the mounted VFS is the root fs).
    def __getattr__(self, name):  # only called for MISSING attributes
        if self.__dict__.get("_vfs") is not None:
            return getattr(self.__dict__["_vfs"], name)
        raise AttributeError(name)


def _assemble_init_program(argv: str, path_addr: int = 900,
                           data_addr: int = 400) -> np.ndarray:
    """PID 1's program: write its argv line into /var/run/last_pid_arg
    (a durable boot record through the VFS), then EXIT 0.

    The write proves the full chain: spatial init -> FILE syscall ->
    ext2 root -> PNG transport."""
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    payload = argv.encode() + b"\x00"
    program = [
        f"LDI r1 {path_addr}",       # path address (RAM-seeded: /var/...)
        f"LDI r2 {data_addr}",       # data address (RAM-seeded: argv)
        f"LDI r3 {len(payload)}",    # length
        "SYSCALL r4 0x03",           # FILE_WRITE through the mounted root
        f"LDI r1 0",                 # EXIT 0 (clean shutdown of PID 1)
        "SYSCALL r0 0x05",
        "HALT",
    ]
    img = asm.assemble(program, width_instrs=8)
    om.close()
    # Pad the image so the engine window is comfortable (the item-26 shape).
    if img.shape[0] < 8:
        padded = np.zeros((8, img.shape[1], 3), dtype=np.uint8)
        padded[: img.shape[0]] = img
        img = padded
    return img


class Kernel:
    """Mounts a GlyphRootFs and runs the boot sequence over the process table."""

    BOOT_RECORD = "/var/run/last_pid_arg"

    def __init__(self, cols_instrs: int = 8, memory_words: int = 16384):
        self._cols_instrs = cols_instrs
        self._memory_words = memory_words
        self.table: GlyphProcessTable | None = None
        self.root: GlyphRootFs | None = None

    def boot(self, root: GlyphRootFs) -> int:
        """Mount the root and start PID 1. Returns PID 1's exit status.

        PID 1 is the FIRST spawn — the process table hands out pid 1 to
        the first task, so the spatial process model's lowest pid is the
        init task, exactly like a Unix boot. A Kernel that already booted
        refuses (a second init would NOT be pid 1 — loud, never silent).
        """
        if self.table is not None:
            raise RootInitError("boot: kernel already booted (PID 1 must be first)")
        vfs = root.mount()
        self.root = root
        self.table = GlyphProcessTable(cols_instrs=self._cols_instrs,
                                       memory_words=self._memory_words)
        # Read the init argv line from the root (the boot record PID 1 runs).
        argv_bytes = vfs.vfs_read(INIT_PATH, 64)
        if not argv_bytes:
            raise RootInitError("boot: /sbin/init is empty")
        argv = argv_bytes.rstrip(b"\x00").decode(errors="strict").strip()
        image = _assemble_init_program(argv)
        pid = self.table.spawn(image, name="init", vfs=vfs, vfs_shared=True)
        if pid != 1:
            raise RootInitError(
                f"boot: PID 1 contract violated — first spawn got pid {pid}")
        # Seed PID 1's RAM: the boot-record path and its argv data.
        cpu = self.table.tasks[pid]["cpu"]
        record = self.BOOT_RECORD
        for i, ch in enumerate(record + "\x00"):
            cpu.memory[900 + i] = ord(ch)
        for i, byte in enumerate(argv.encode() + b"\x00"):
            cpu.memory[400 + i] = byte
        status = self.table.wait(pid)
        return status

    def shutdown_sync(self) -> int:
        """Persist PID 1's writes to the root PNG (the reboot contract)."""
        if self.root is None or self.root._vfs is None:
            raise RootInitError("shutdown_sync: no mounted root")
        rc = self.root._vfs.sync()
        if rc != 0:
            raise RootInitError(f"shutdown_sync: sync refused rc={rc}")
        return rc

    def close(self):
        if self.table is not None:
            self.table.close()
            self.table = None


def boot(root_png_path: str, sync_on_shutdown: bool = True) -> tuple[int, Kernel]:
    """One-line boot: mount + PID 1 + reap. Returns (exit_status, kernel)."""
    k = Kernel()
    status = k.boot(GlyphRootFs(root_png_path))
    if sync_on_shutdown:
        k.shutdown_sync()
    return status, k
