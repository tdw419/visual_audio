#!/usr/bin/env python3
"""
visual_audio_container.py -- Python API wrapper for va_container operations.

This provides a clean, importable interface that autonomous agents can use
directly without subprocess overhead. All operations use the underlying
va_container functions but wrap them in a Pythonic Container class with
context managers and proper locking.

Usage:
    from visual_audio_container import Container

    with Container("visual_audio.mkv") as c:
        data = c.read("pixel_mind_repl.py")
        c.add("new_thought.txt", "content", role="thought")
        entries = c.list()
        c.patch(x, y, pixel_data)
"""

import contextlib
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from va_container import (
    DIR_MAGIC,
    FRAME_BYTES,
    FRAME_SIZE,
    MAX_PAYLOAD_PER_FRAME,
    add_entry,
    chunk_to_frame,
    container_lock,
    frame_to_chunk,
    load_container,
    read_directory,
    read_entry_streamed,
    read_frame_range,
    read_frames,
    save_container,
)
from mkv_infinite_map import hilbert_d2xy, hilbert_xy2d


class Container:
    """Pythonic API for Visual Audio MKV containers.

    Thread-safe: all modifications go through the .lock file via container_lock.
    Efficient reads: read_entry() uses seek to avoid decoding entire container.
    """

    def __init__(self, mkv_path: str | Path):
        self.mkv_path = Path(mkv_path)
        self._directory: Optional[dict] = None
        self._frames: Optional[list] = None

    def __enter__(self) -> "Container":
        return self

    def __exit__(self, *args):
        # Any unsaved changes would need explicit save() call
        # This just ensures cleanup if needed
        pass

    # ---------------------------------------------------------------- read operations

    def read(self, name: str) -> bytes:
        """Read an entry by name, using seek to decode only that entry."""
        directory = self._get_directory()
        return read_entry_streamed(self.mkv_path, directory, name)

    def read_text(self, name: str) -> str:
        """Read an entry as UTF-8 text (with error handling)."""
        raw = self.read(name)
        try:
            return raw.decode()
        except UnicodeDecodeError:
            # Fallback: decode with error replacement for display purposes
            return raw.decode(errors="replace")

    def read_json(self, name: str) -> dict:
        """Read an entry as JSON."""
        return json.loads(self.read_text(name))

    def list(self, filter_role: Optional[str] = None) -> list[dict]:
        """List all entries, optionally filtering by role."""
        directory = self._get_directory()
        entries = directory.get("entries", [])
        if filter_role:
            entries = [e for e in entries if e.get("role") == filter_role]
        return entries

    def verify(self) -> dict[str, Any]:
        """Verify all entries' CRC and sha256. Returns status dict."""
        directory = self._get_directory()
        status = {"total": len(directory["entries"]), "valid": 0, "invalid": []}

        for entry in directory["entries"]:
            name = entry["name"]
            expected_sha = entry["sha256"]
            actual_sha = hashlib.sha256(self.read(name)).hexdigest()
            if actual_sha == expected_sha:
                status["valid"] += 1
            else:
                status["invalid"].append({
                    "name": name,
                    "expected": expected_sha,
                    "actual": actual_sha,
                })

        return status

    # ---------------------------------------------------------------- write operations (need lock)

    @contextlib.contextmanager
    def _write_lock(self):
        """Internal: acquire lock, load fresh state.

        load_container() returns ALL frames including the leading directory
        frames. save_container()/add_entry() expect payload-only frames (they
        prepend the directory themselves) -- passing the raw list back in
        double-counts and re-embeds stale directory frames, corrupting the
        offset table. Strip them here, once, the same way cmd_add() does in
        va_container.py.
        """
        with container_lock(self.mkv_path):
            directory, frames = load_container(self.mkv_path)
            self._directory = directory
            self._frames = frames[directory.get("_dir_frames", 1):]
            yield

    def add(
        self,
        name: str,
        payload: str | bytes,
        role: str = "code",
        note: str = "",
    ) -> dict:
        """Add a new entry to the container (requires lock)."""
        if isinstance(payload, str):
            payload = payload.encode()

        with self._write_lock():
            assert self._directory is not None, "directory should be loaded in _write_lock"
            assert self._frames is not None, "frames should be loaded in _write_lock"
            add_entry(
                self._directory,
                self._frames,
                name,
                role,
                note,
                payload,
            )
            save_container(self._directory, self._frames, self.mkv_path)

        # Reload to get updated entry metadata
        entry = self._get_entry(name)
        return entry

    def update(self, name: str, payload: str | bytes) -> dict:
        """Replace an existing entry (appends history)."""
        if isinstance(payload, str):
            payload = payload.encode()

        with self._write_lock():
            assert self._directory is not None, "directory should be loaded in _write_lock"
            assert self._frames is not None, "frames should be loaded in _write_lock"
            directory = self._directory
            frames = self._frames

            # Find existing entry
            entry = None
            for e in directory["entries"]:
                if e["name"] == name:
                    entry = e
                    break

            if not entry:
                raise ValueError(f"entry does not exist: {name}")

            # Save old version to history
            if "history" not in entry:
                entry["history"] = []
            entry["history"].append({
                "frames": entry["frames"].copy(),
                "length": entry["length"],
                "sha256": entry["sha256"],
                "ts": entry["ts"],
            })

            # Write new version
            chunks = [payload[i:i + MAX_PAYLOAD_PER_FRAME]
                      for i in range(0, len(payload), MAX_PAYLOAD_PER_FRAME)]
            start = directory.get("_dir_frames", 1) + len(frames)
            frames.extend(chunk_to_frame(c) for c in chunks)

            # Update entry metadata
            entry["frames"] = [start, len(chunks)]
            entry["length"] = len(payload)
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["ts"] = time.time()

            save_container(directory, frames, self.mkv_path)

        return self._get_entry(name)

    def patch(self, x: int, y: int, png_path: str | Path, name: Optional[str] = None,
              role: str = "code", note: str = "") -> dict:
        """Paint a PNG into a specific (x, y) tile (Hilbert mapping)."""
        png_path = Path(png_path)

        with self._write_lock():
            assert self._directory is not None, "directory should be loaded in _write_lock"
            assert self._frames is not None, "frames should be loaded in _write_lock"
            directory = self._directory
            frames = self._frames

            # Generate manifest to find next writable tile
            manifest = self._generate_manifest(directory)
            target_distance = hilbert_xy2d(manifest["order"], x, y)
            entries_count = len(manifest["tiles"])

            # Enforce strict write-once semantics: only the next tile is writable
            if target_distance != entries_count:
                raise ValueError(
                    f"tile ({x}, {y}) at distance {target_distance} is not "
                    f"the next writable position (distance {entries_count})"
                )

            # Read the PNG payload
            with open(png_path, "rb") as f:
                payload = f.read()

            # Add the entry
            add_entry(
                directory,
                frames,
                name or f"tile_{x}_{y}",
                role,
                note,
                payload,
            )
            save_container(directory, frames, self.mkv_path)

        return self._get_entry(name or f"tile_{x}_{y}")

    # ---------------------------------------------------------------- spatial operations

    def get_manifest(self, order: int = 10) -> dict:
        """Generate Hilbert-space manifest for the container."""
        directory = self._get_directory()
        return self._generate_manifest(directory, order)

    def _generate_manifest(self, directory: dict, order: int = 10) -> dict:
        """Generate manifest from directory (internal)."""
        tiles = []
        for i, entry in enumerate(directory["entries"]):
            x, y = hilbert_d2xy(order, i)
            tiles.append({
                "name": entry["name"],
                "x": x,
                "y": y,
                "frame_start": entry["frames"][0],
                "frame_count": entry["frames"][1],
                "role": entry.get("role", ""),
            })

        return {
            "order": order,
            "grid_size": 2**order,
            "tile_count": len(tiles),
            "tiles": tiles,
        }

    def get_ascii_viewport(self, x0: int, y0: int, w: int, h: int, order: int = 10) -> str:
        """Return a semantic ASCII representation of a viewport on the map."""
        manifest = self.get_manifest(order)
        by_coord = {(t["x"], t["y"]): t for t in manifest["tiles"]}
        
        ROLE_CHARS = {
            "thought": "?",
            "summary": "S",
            "terrain_tile": "~",
            "code": "{",
            "bootstrap": "^",
            "kernel": "K",
            "tools": "*",
            "message": "@",
            "emulator": "E",
            "reference": "R",
            "content": "C"
        }
        
        lines = []
        for y in range(y0, y0 + h):
            row = []
            for x in range(x0, x0 + w):
                t = by_coord.get((x, y))
                if t:
                    char = ROLE_CHARS.get(t.get("role", ""), "#")
                    row.append(char)
                else:
                    row.append(".")
            lines.append("".join(row))
            
        return "\n".join(lines)

    # ---------------------------------------------------------------- private helpers

    def _get_directory(self) -> dict:
        """Lazy-load directory (no lock needed for reads)."""
        if self._directory is None:
            self._directory = read_directory(self.mkv_path)
        return self._directory

    def _get_entry(self, name: str) -> dict:
        """Get entry metadata by name."""
        for entry in self._get_directory()["entries"]:
            if entry["name"] == name:
                return entry
        raise KeyError(f"no such entry: {name}")


# ---------------------------------------------------------------- convenience functions

def quick_add(mkv_path: str, name: str, payload: str | bytes, role: str = "code") -> dict:
    """One-shot add without context manager (for scripts)."""
    with Container(mkv_path) as c:
        return c.add(name, payload, role=role)


def quick_read(mkv_path: str, name: str) -> bytes:
    """One-shot read without context manager (for scripts)."""
    with Container(mkv_path) as c:
        return c.read(name)


def quick_list(mkv_path: str, filter_role: Optional[str] = None) -> list[dict]:
    """One-shot list without context manager (for scripts)."""
    with Container(mkv_path) as c:
        return c.list(filter_role=filter_role)