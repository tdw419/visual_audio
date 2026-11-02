"""glyph_loader.py — CLAIM QUEUE item 30: ext2 spatial executable loader.

Load a glyph PROGRAM image from the ext2 root (the item-25/28 VFS-PNG
disk), verify it against its recorded SHA-256 fold, and exec it into the
spatial process model (item-26 table, item-29 containment).

Layer contract:

  - VFS-1 (tools/png_vfs.py): ext2 in a PNG — the disk transport.
  - VFS-2/3 (tools/glyph_vfs.py): 0x03/0x04 file access + staged writes.
  - item-28 (tools/glyph_root_init.py): Kernel.boot — PID 1 is the FIRST
    spawn of the process table.
  - item-26/29 (tools/glyph_process.py + tools/glyph_containment.py):
    spawn(image, tile=...) — fresh GlyphCPUv2 per task, optional tile.

item-30 is a HOST-side loader: it adds NO syscall number, NO engine
change, and NO guest-visible ABI (the WGSL twin contract is untouched;
the TICKET_ITEM8 false-success class is structurally avoided). exec in
this lane is the item-26 shape: the recovered image is a NEW spawn —
PID 1 never displaces itself; an exec'd task takes the NEXT pid.

Integrity: the exec format is the PROGRAM IMAGE ITSELF plus a sidecar
digest file (b".sha256" suffix). The digest is written at load-store
time by store_program() and verified at exec time — a corrupted payload
(the B5 leg flips a payload byte) fails the fold-check and is refused
loud. The digest is stored in the SAME directory tree, so it inherits
the ext2 PNG transport; it is NOT a parse of the program bytes (the
loader never parses glyph opcodes — the engine remains the only
decoder, the item-24 discipline).
"""
from __future__ import annotations

import hashlib

import numpy as np

from tools.glyph_isa_v2 import INSTR_WIDTH  # px per instruction column
from tools.glyph_process import GlyphProcessTable


class LoaderError(Exception):
    """Raised when a program cannot be loaded from disk — loud, never silent."""


def _digest_path(path: str) -> str:
    if not path.startswith("/"):
        raise LoaderError(f"program path must be absolute, got {path!r}")
    return path + ".sha256"


def store_program(vfs, path: str, image: np.ndarray) -> None:
    """Write a glyph program image + its SHA-256 sidecar to the root.

    `vfs` is a mounted GlyphVfs (item-25 arms). The caller syncs.
    """
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.dtype != np.uint8:
        raise LoaderError("store_program: image must be an HxWx3 uint8 ndarray")
    raw = image.tobytes()
    if vfs.vfs_write(path, raw) != 0:
        raise LoaderError(f"store_program: vfs_write({path}) refused")
    digest = hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n"
    if vfs.vfs_write(_digest_path(path), digest) != 0:
        raise LoaderError(f"store_program: vfs_write({_digest_path(path)}) refused")


def load_program(png_path: str, path: str, table: GlyphProcessTable,
                 name: str = "", tile=None, **spawn_kw) -> int:
    """Recover a program image from the ext2-PNG root and spawn it.

    Returns the pid. Raises LoaderError on: missing program, missing or
    malformed digest, digest mismatch (corruption), or undecodable image
    bytes. The digest check is the load-time containment: a corrupted
    payload never reaches spawn.
    """
    from tools.glyph_vfs import GlyphVfs  # local: avoid import cycle at module load

    vfs = GlyphVfs(png_path)
    raw = vfs.vfs_read(path, 1 << 20)
    if raw is None:
        raise LoaderError(f"load_program: {path} not found in {png_path}")
    digest_expected = vfs.vfs_read(_digest_path(path), 128)
    if digest_expected is None:
        raise LoaderError(f"load_program: no digest sidecar for {path}")
    got = hashlib.sha256(raw).hexdigest().encode("ascii")
    want = digest_expected.split(b"\n")[0]
    if got != want:
        raise LoaderError(
            f"load_program: digest mismatch for {path}: "
            f"expected {want.decode(errors='replace')}, got {got.decode()}"
        )
    try:
        image = np.frombuffer(raw, dtype=np.uint8)
        # Reshape to the engine window: rows x (cols_instrs * INSTR_WIDTH)
        # x 3 — the engine's image geometry (INSTR_WIDTH px per instruction
        # column), recovered from the digest-checked bytes, never guessed.
        image = image.reshape(-1, table._cols_instrs * INSTR_WIDTH, 3)
    except ValueError as exc:
        raise LoaderError(f"load_program: {path} is not a decodable image: {exc}")
    return table.spawn(image, name=name, tile=tile, **spawn_kw)


def exec_program(png_path: str, path: str, kernel, name: str = "",
                 tile=None, **spawn_kw) -> int:
    """Exec a disk-stored program on a booted Kernel (the PID-1-safe shape).

    exec = a NEW spawn on the kernel's EXISTING process table (the
    recovered image never displaces PID 1; the exec'd task takes the
    NEXT pid — ≥ 2 for any booted kernel). Shares the kernel's mounted
    root VFS (the item-27 U1 shared-VFS contract).
    """
    if kernel.table is None:
        raise LoaderError("exec_program: kernel not booted")
    table = kernel.table
    vfs = kernel.root._vfs  # the mounted root VFS (shared channel)
    raw = vfs.vfs_read(path, 1 << 20)
    if raw is None:
        raise LoaderError(f"exec_program: {path} not found in the mounted root")
    digest_expected = vfs.vfs_read(_digest_path(path), 128)
    if digest_expected is None:
        raise LoaderError(f"exec_program: no digest sidecar for {path}")
    got = hashlib.sha256(raw).hexdigest()
    want = digest_expected.split(b"\n")[0]
    if got != want.decode("ascii"):
        raise LoaderError(
            f"exec_program: digest mismatch for {path}: "
            f"expected {want.decode(errors='replace')}, got {got}"
        )
    try:
        image = np.frombuffer(raw, dtype=np.uint8).reshape(-1, table._cols_instrs * INSTR_WIDTH, 3)
    except ValueError as exc:
        raise LoaderError(f"exec_program: {path} is not a decodable image: {exc}")
    return table.spawn(image, name=name, tile=tile, vfs=vfs, vfs_shared=True, **spawn_kw)
