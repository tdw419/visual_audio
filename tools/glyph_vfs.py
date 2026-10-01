#!/usr/bin/env python3
"""glyph_vfs.py — item-25 VFS-2/3: a glyph-attachable VFS backend.

Layer contract (item-25, unblocked by operator sign-off 2026-09-26, ec5fea0f):

  - VFS-2 (re-route): when a GlyphVfs instance is ATTACHED to a GlyphCPUv2,
    the FILE syscalls (0x03 write / 0x04 read / 0x13 list) operate on the
    VFS's ext2 disk image via e2progs debugfs instead of the host
    filesystem. When NO VFS is attached (the default for every existing
    caller), the handlers take the exact landed host path — the diff to
    the handlers is an early `if self.vfs:` arm, nothing else moves.
  - VFS-3 (writeback): writes land in a host-side staging directory (an
    overlay over the ext2 image). `GlyphVfs.sync()` commits the staging
    directory into the ext2 image (debugfs -w) and re-wraps the image into
    the PNG disk via the landed VFS-1 transport (tools/png_vfs.py). Until
    sync(), a fresh boot (a NEW GlyphVfs from the same PNG) does NOT see
    the write — persistence is gated on sync, like a dirty page cache.

ext2 content via debugfs ONLY (the item-24 spec discipline: this module
never parses or emits ext2 structures; ext2 content is produced/validated
by host e2progs: mke2fs/debugfs/e2fsck).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import tools.png_vfs as png_vfs


class GlyphVfsError(Exception):
    """Raised on VFS misuse — loud, never silent."""


def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, **kw)


class GlyphVfs:
    """Attachable VFS: ext2-in-a-file content, PNG transport, staged writes.

    Lifecycle:
        v = GlyphVfs.format(png_path)      # or GlyphVfs(png_path) to load
        v.attach(cpu)                      # syscalls 0x03/0x04/0x13 re-route
        ... program writes via syscalls ...   # staged host-side
        v.sync()                           # commit staging -> ext2 -> PNG
        # a FRESH GlyphVfs(png_path) then sees synced content (reboot leg)
    """

    def __init__(self, png_path: str):
        self.png_path = str(Path(png_path).resolve())
        self._attached_cpus: list = []
        self._staging: str | None = None    # staging dir (overlay root)
        self._dirty = False
        self._disk_path: str | None = None  # raw ext2 image path
        self._disk: bytes | None = None     # raw ext2 image bytes (loaded)

    # ── format / load ────────────────────────────────────────────────────
    @classmethod
    def format(cls, png_path: str, size_bytes: int = 1 << 20,
               blocksize: int = 1024) -> "GlyphVfs":
        """Create a fresh ext2 image (mke2fs) and wrap it to the PNG transport.

        Geometry: default 1 MiB disk — mke2fs -b 1024 gives 1024 blocks;
        far under the VFS-1 canvas budget (2048x2048 = 12.58 MB payload),
        so a full-disk wrap always fits one PNG.
        """
        png_path = str(Path(png_path).resolve())
        work = tempfile.mkdtemp(prefix="glyph_vfs_fmt_")
        disk = os.path.join(work, "disk.img")
        try:
            r = _run(["mke2fs", "-q", "-F", "-b", str(blocksize),
                      "-t", "ext2", disk, f"{size_bytes // 1024}k"])
            if r.returncode != 0:
                raise GlyphVfsError(
                    f"mke2fs failed rc={r.returncode}: "
                    f"{r.stderr.decode(errors='replace').strip()}")
            with open(disk, "rb") as f:
                raw = f.read()
        finally:
            shutil.rmtree(work, ignore_errors=True)
        png_vfs.wrap(raw, png_path)
        v = cls(png_path)
        v._disk = raw
        return v

    def _ensure_loaded(self) -> None:
        if self._disk is not None:
            return
        raw = png_vfs.unwrap(self.png_path)
        self._disk = raw

    def _ensure_staging(self) -> str:
        """Materialize the ext2 image + staging dir on first use."""
        self._ensure_loaded()
        if self._staging is None:
            work = tempfile.mkdtemp(prefix="glyph_vfs_stage_")
            self._disk_path = os.path.join(work, "disk.img")
            with open(self._disk_path, "wb") as f:
                f.write(self._disk)
            self._staging = os.path.join(work, "root")
            os.makedirs(self._staging, exist_ok=True)
        return self._staging

    # ── attach / detach ──────────────────────────────────────────────────
    def attach(self, cpu) -> None:
        """Attach to a GlyphCPUv2: its FILE syscalls re-route to this VFS."""
        cpu.vfs = self
        if self not in self._attached_cpus:
            self._attached_cpus.append(cpu)

    def detach(self, cpu) -> None:
        cpu.vfs = None
        if self in self._attached_cpus:
            self._attached_cpus.remove(cpu)

    # ── syscall operations (called from GlyphCPUv2._handle_syscall) ──────
    def vfs_write(self, path: str, data: bytes) -> int:
        """0x03 on the VFS: stage the write under the session root.

        Containment: paths are guest-relative (leading '/' stripped,
        '..' refused) and resolve under the staging root — the same
        contract L1Session.resolve enforces host-side, mirrored here so a
        staged write can never escape the disk image.
        Returns 0 on success, -1 on refusal (errno-style, rc contract).
        """
        rel = self._guest_rel(path)
        if rel is None:
            return -1
        root = self._ensure_staging()
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        self._dirty = True
        return 0

    def vfs_read(self, path: str, max_len: int) -> bytes | None:
        """0x04 on the VFS: read staged bytes, else the ext2 image.

        Precedence: staging overlay first (the dirty page cache), then the
        image as of last sync. None == not found (rc -1 at the handler).
        """
        rel = self._guest_rel(path)
        if rel is None:
            return None
        root = self._ensure_staging()
        staged = os.path.join(root, rel)
        if os.path.isfile(staged):
            with open(staged, "rb") as f:
                return f.read(max_len)
        # Fall through to the image: extract via debugfs into a temp dir.
        if self._disk_path is None:
            return None
        if self._image_has(rel):
            out = tempfile.mkdtemp(prefix="glyph_vfs_rd_")
            dest = os.path.join(out, os.path.basename(rel) or "payload")
            r = _run(["debugfs", "-R", f'dump "/{rel}" "{dest}"',
                      self._disk_path])
            if r.returncode != 0:
                return None
            with open(dest, "rb") as f:
                data = f.read(max_len)
            os.remove(dest)
            os.rmdir(out)
            return data
        return None

    def vfs_list(self, path: str, max_bytes: int) -> list[str] | None:
        """0x13 on the VFS: directory listing (staged ∪ image).

        Returns the name list, [] for an empty/absent-but-root dir,
        None on refusal (not a directory anywhere / containment breach).
        Names truncated whole to max_bytes — same contract as the host
        0x13 arm (never a partial name).
        """
        rel = self._guest_rel(path)
        if rel is None:
            return None
        root = self._ensure_staging()
        staged_dir = os.path.join(root, rel)
        names: dict[str, None] = {}
        if os.path.isdir(staged_dir):
            for n in sorted(os.listdir(staged_dir)):
                names[n] = None
        if rel in ("", "."):
            image_names = self._image_list("/")
        else:
            image_names = self._image_list("/" + rel)
        if image_names is None and not os.path.isdir(staged_dir):
            return None
        for n in image_names or []:
            names.setdefault(n, None)
        ordered = sorted(names)
        blob = bytearray()
        out: list[str] = []
        for name in ordered:
            piece = name.encode() + b"\0"
            if len(blob) + len(piece) > max_bytes:
                break  # whole-name truncation
            blob += piece
            out.append(name)
        return out

    # ── sync / persistence (VFS-3) ───────────────────────────────────────
    def sync(self) -> int:
        """Commit the staging overlay into the ext2 image, re-wrap the PNG.

        debugfs -w writes each staged file at its guest path; e2fsck -fn
        validates the result BEFORE the wrap (a corrupt image never
        replaces the disk). Returns 0, or -1 and leaves the previous
        image intact on any failure.
        """
        if not self._dirty:
            return 0
        root = self._ensure_staging()
        # Stage every file under the staging root into the image.
        # debugfs 1.47: `write <native file> <new file>` (verified via
        # `debugfs -R "help write"` usage error); `rm` is idempotent-ish
        # (absent file -> error text, rc 0) and is issued first so a
        # re-sync of an existing name replaces it.
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                abs_path = os.path.join(dirpath, name)
                rel = os.path.relpath(abs_path, root)
                parent = os.path.dirname(rel)
                # mkdir -p equivalent: walk segments top-down; DEFECT-32
                # fix (item-28, this tree): debugfs mkdir on an EXISTING
                # directory allocates + links a fresh dir inode and THEN
                # fails with "already exists" (rc 0!), orphaning the
                # inode — e2fsck -fn rc=4 and this sync refuses. Probe
                # first with stat and only mkdir what is missing.
                segs = [s for s in parent.split("/") if s] if parent else []
                partial = ""
                for seg in segs:
                    partial += "/" + seg
                    if not self._image_dir_exists(partial):
                        _run(["debugfs", "-w", "-R",
                              f'mkdir "{partial}"', self._disk_path])
                _run(["debugfs", "-w", "-R",
                      f'rm "/{rel}"', self._disk_path])
                r = _run(["debugfs", "-w", "-R",
                          f'write "{abs_path}" "/{rel}"', self._disk_path])
                if r.returncode != 0 or "File exists" in r.stderr.decode(
                        errors="replace"):
                    return -1
        # Validate BEFORE the image replaces the disk (loud, never silent).
        chk = _run(["e2fsck", "-fn", self._disk_path])
        if chk.returncode not in (0, 1):
            return -1
        with open(self._disk_path, "rb") as f:
            new_raw = f.read()
        try:
            png_vfs.wrap(new_raw, self.png_path)
        except png_vfs.PngVfsError:
            return -1
        self._disk = new_raw
        # Staged content is now in the image; the overlay cache is clean.
        shutil.rmtree(root, ignore_errors=True)
        self._staging = None
        self._disk_path = None
        self._dirty = False
        return 0

    def dirty(self) -> bool:
        return self._dirty

    # ── image-side probes (debugfs; never parse ext2 ourselves) ─────────
    def _image_has(self, rel: str) -> bool:
        self._ensure_staging()  # materializes _disk_path from the PNG
        r = _run(["debugfs", "-R", f'stat "/{rel}"', self._disk_path])
        # debugfs 1.47 stat prints "Type: regular" for files (verified);
        # directories show "Type: directory".
        return r.returncode == 0 and b"Type: regular" in r.stdout

    def _image_dir_exists(self, img_dir: str) -> bool:
        """True if `img_dir` exists in the image AND is a directory.

        DEFECT-32 helper: debugfs mkdir on an existing directory orphans
        an inode (e2fsck -fn rc=4, measured this tick), so sync() must
        probe before mkdir. A FILE at the path counts as not-exists (the
        subsequent mkdir's error then surfaces loudly at write time).
        """
        self._ensure_staging()
        r = _run(["debugfs", "-R", f'stat "{img_dir}"', self._disk_path])
        return r.returncode == 0 and b"Type: directory" in r.stdout

    def _image_list(self, img_dir: str) -> list[str] | None:
        """List an image directory via debugfs ls -l (name-only use).

        debugfs `ls -l` lines end with the name; rc==0 with no output
        means an empty dir. None only if the dir does not exist.
        """
        self._ensure_staging()
        r = _run(["debugfs", "-R", f'ls -l "{img_dir}"', self._disk_path])
        if r.returncode != 0:
            return None
        combined = (r.stdout + r.stderr).decode(errors="replace")
        if ("not a directory" in combined.lower()
                or "File not found" in combined):
            return None
        out = combined
        names: list[str] = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 9:
                names.append(parts[-1])
        # debugfs ls -l emits a header line and . / .. entries — drop them.
        return [n for n in names if n not in (".", "..")]

    # ── containment ──────────────────────────────────────────────────────
    @staticmethod
    def _guest_rel(path: str) -> str | None:
        """Guest path -> staging-relative, or None on refusal.

        Leading '/' is stripped (guest-absolute is fine — there is only
        one root); '..' escapes and empty results of dot-segments are
        normalized the L1Session.resolve way.
        """
        name = (path or "").strip()
        if not name:
            return None
        parts: list[str] = []
        for seg in name.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
                    continue
                return None  # escapes the root
            if len(seg) > 64:
                return None
            parts.append(seg)
        return "/".join(parts)
