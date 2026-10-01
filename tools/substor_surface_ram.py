#!/usr/bin/env python3
"""substor_surface_ram.py — Substrate-backed RAM store for Geometry OS (SUBSTOR-1).

A word-addressed memory store whose backing medium is a substrate surface
(dense PNG image using GH-8b pixel-FS word encoding, 2 px/word: lo24 in RGB of
even pixel, hi8 in Blue of odd pixel, and/or Memory Palace PNG frame via
tools/geos_memory_palace_viz.py::PalaceState / render_to_png / decode_png).

Every write is logged with writer attribution + monotonic write_id (DEFECT-20
discipline: see tools/geos_witness.py and the write_id / writer sidecar fields
in tools/geos_emit.py).

Provides an explicit declared-region mechanism:
- Writers declare the word ranges [start_word, end_word) they own.
- Any write outside a writer's declared regions is logged and reported as a CLOBBER
  (not silently accepted), and turns substrate witness verification RED.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import numpy as np
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "tools"))

try:
    from geos_memory_palace_viz import (
        GeOSMemoryPalaceVisualizer,
        PalaceState,
        PalaceTile,
    )
except ImportError:
    PalaceState = None  # type: ignore
    PalaceTile = None  # type: ignore
    GeOSMemoryPalaceVisualizer = None  # type: ignore


class SubstorError(Exception):
    """Base exception for substrate storage operations."""
    pass


class ClobberError(SubstorError):
    """Raised when a write lands outside declared regions in strict mode."""
    pass


class WitnessError(SubstorError):
    """Raised when substrate witness verification fails."""
    pass


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubstorSurfaceRAM:
    """Substrate-backed word-addressed RAM store.

    Words are mapped to pixels on a substrate surface image. Persists to a PNG file
    along with a sidecar metadata JSON file tracking writer attribution, monotonic
    write IDs, declared regions, and clobbers.
    """

    def __init__(
        self,
        size_words: int = 1024,
        surface_path: Optional[Union[str, Path]] = None,
        img_width: int = 64,
        img_height: int = 32,
    ):
        self.size_words = int(size_words)
        self.surface_path = Path(surface_path) if surface_path else None
        self.meta_path = (
            self.surface_path.with_suffix(".meta.json") if self.surface_path else None
        )

        # Ensure grid has enough capacity for size_words (2 pixels per word)
        min_pixels = self.size_words * 2
        w = max(img_width, 16)
        h = max(img_height, (min_pixels + w - 1) // w)
        self.img_w = w
        self.img_h = h

        # Surface pixel buffer (RGB, 3 channels)
        self.image = np.zeros((self.img_h, self.img_w, 3), dtype=np.uint8)

        # Declared regions: writer -> list of (start_word, end_word)
        self.declared_regions: Dict[str, List[Tuple[int, int]]] = {}

        # Per-word attribution: word_idx -> {writer, write_id, written_at, value}
        self.word_attribution: Dict[int, Dict[str, Any]] = {}

        # Monotonic write counter and audit log
        self.write_id_counter: int = 0
        self.write_log: List[Dict[str, Any]] = []

        # Clobber tracking: writes outside declared regions
        self.clobbers: List[Dict[str, Any]] = []
        self.clobbered_words: Set[int] = set()

        if self.surface_path and self.surface_path.exists():
            self.reload_from_surface()

    def declare_region(self, writer: str, start_word: int, end_word: int) -> None:
        """Declare that `writer` owns the word range [start_word, end_word)."""
        if not writer or not isinstance(writer, str):
            raise ValueError(f"Invalid writer name: {writer!r}")
        start = int(start_word)
        end = int(end_word)
        if start < 0 or end < start or end > self.size_words:
            raise ValueError(
                f"Invalid region [{start}, {end}) for store size {self.size_words}"
            )
        self.declared_regions.setdefault(writer, []).append((start, end))

    def is_declared(self, writer: str, word: int) -> bool:
        """Check if `word` falls within any declared region for `writer`."""
        if not writer:
            return False
        regions = self.declared_regions.get(writer, [])
        return any(start <= word < end for start, end in regions)

    def _encode_word_to_pixels(self, word_idx: int, value: int) -> None:
        """Encode a 32-bit word into 2 pixels (GH-8b layout)."""
        val = int(value) & 0xFFFFFFFF
        lin = (word_idx * 2) % (self.img_w * self.img_h)
        lin2 = (word_idx * 2 + 1) % (self.img_w * self.img_h)
        self.image[lin // self.img_w, lin % self.img_w] = (
            (val >> 16) & 0xFF,
            (val >> 8) & 0xFF,
            val & 0xFF,
        )
        self.image[lin2 // self.img_w, lin2 % self.img_w] = (
            0,
            0,
            (val >> 24) & 0xFF,
        )

    def _decode_word_from_pixels(self, word_idx: int) -> int:
        """Decode a 32-bit word from 2 pixels (GH-8b layout)."""
        lin = (word_idx * 2) % (self.img_w * self.img_h)
        lin2 = (word_idx * 2 + 1) % (self.img_w * self.img_h)
        p0 = self.image[lin // self.img_w, lin % self.img_w]
        p1 = self.image[lin2 // self.img_w, lin2 % self.img_w]
        lo = (int(p0[0]) << 16) | (int(p0[1]) << 8) | int(p0[2])
        hi = int(p1[2])
        return ((lo | (hi << 24)) & 0xFFFFFFFF)

    def write_word(
        self,
        word_idx: int,
        value: int,
        writer: str = "unattributed",
        strict: bool = False,
    ) -> int:
        """Write a single word with writer attribution and monotonic write_id.

        If the write is outside writer's declared regions, logs a clobber.
        """
        idx = int(word_idx)
        if not (0 <= idx < self.size_words):
            raise IndexError(f"Word index {idx} out of range [0, {self.size_words})")

        self.write_id_counter += 1
        write_id = self.write_id_counter
        val = int(value) & 0xFFFFFFFF
        ts = _iso_now()

        # Check declared regions
        if not self.is_declared(writer, idx):
            clobber_record = {
                "word": idx,
                "writer": writer,
                "write_id": write_id,
                "value": val,
                "declared_regions": self.declared_regions.get(writer, []),
                "timestamp": ts,
            }
            self.clobbers.append(clobber_record)
            self.clobbered_words.add(idx)
            if strict:
                raise ClobberError(
                    f"CLOBBER: writer '{writer}' wrote word {idx} outside declared regions {self.declared_regions.get(writer, [])}"
                )

        # Write to substrate surface image
        self._encode_word_to_pixels(idx, val)

        # Record attribution
        attr_record = {
            "writer": writer,
            "write_id": write_id,
            "written_at": ts,
            "value": val,
        }
        self.word_attribution[idx] = attr_record
        self.write_log.append({"word": idx, **attr_record})

        if self.surface_path:
            self.commit_surface()

        return write_id

    def write_words(
        self,
        start_word: int,
        words: Sequence[int],
        writer: str = "unattributed",
        strict: bool = False,
    ) -> List[int]:
        """Write a sequence of words starting at start_word."""
        write_ids = []
        for offset, val in enumerate(words):
            wid = self.write_word(start_word + offset, val, writer=writer, strict=strict)
            write_ids.append(wid)
        return write_ids

    def read_word(self, word_idx: int) -> int:
        """Read a single word directly from the substrate surface."""
        idx = int(word_idx)
        if not (0 <= idx < self.size_words):
            raise IndexError(f"Word index {idx} out of range [0, {self.size_words})")
        return self._decode_word_from_pixels(idx)

    def get_words(self, start_word: int, count: int) -> List[int]:
        """Read count words starting at start_word directly from the surface."""
        start = int(start_word)
        cnt = int(count)
        if start < 0 or start + cnt > self.size_words:
            raise IndexError(
                f"Range [{start}, {start + cnt}) out of bounds [0, {self.size_words})"
            )
        return [self._decode_word_from_pixels(start + i) for i in range(cnt)]

    def commit_surface(
        self, path: Optional[Union[str, Path]] = None
    ) -> Tuple[Path, Path]:
        """Save the surface image to PNG and write sidecar metadata JSON."""
        target_png = Path(path) if path else self.surface_path
        if not target_png:
            raise ValueError("No surface_path provided to commit_surface")

        target_png.parent.mkdir(parents=True, exist_ok=True)
        target_meta = target_png.with_suffix(".meta.json")

        # Save PNG
        img = Image.fromarray(self.image)
        scratch_png = target_png.with_suffix(".png.tmp")
        img.save(scratch_png, format="PNG")
        os.replace(scratch_png, target_png)

        # Checksum
        img_md5 = hashlib.md5(target_png.read_bytes()).hexdigest()

        # Save sidecar metadata JSON
        last_write = self.write_log[-1] if self.write_log else {}
        meta_payload = {
            "version": "substor_v1",
            "size_words": self.size_words,
            "write_id": self.write_id_counter,
            "writer": last_write.get("writer", "unattributed"),
            "written_at": last_write.get("written_at", _iso_now()),
            "image_file": str(target_png.name),
            "image_md5": img_md5,
            "declared_regions": {
                k: [list(r) for r in v] for k, v in self.declared_regions.items()
            },
            "clobbers": self.clobbers,
            "word_attribution": {
                str(k): v for k, v in self.word_attribution.items()
            },
        }

        scratch_meta = target_meta.with_suffix(".meta.json.tmp")
        scratch_meta.write_text(json.dumps(meta_payload, indent=2))
        os.replace(scratch_meta, target_meta)

        self.surface_path = target_png
        self.meta_path = target_meta
        return target_png, target_meta

    def reload_from_surface(self, path: Optional[Union[str, Path]] = None) -> None:
        """Reload surface image and metadata from disk."""
        target_png = Path(path) if path else self.surface_path
        if not target_png or not target_png.exists():
            raise FileNotFoundError(f"Surface file not found: {target_png}")

        img = Image.open(target_png).convert("RGB")
        self.image = np.array(img, dtype=np.uint8)
        self.img_h, self.img_w, _ = self.image.shape

        target_meta = target_png.with_suffix(".meta.json")
        if target_meta.exists():
            try:
                meta = json.loads(target_meta.read_text())
                self.write_id_counter = int(meta.get("write_id", 0) or 0)
                self.clobbers = meta.get("clobbers", [])
                self.clobbered_words = {c["word"] for c in self.clobbers if "word" in c}
                self.declared_regions = {
                    k: [tuple(r) for r in v]
                    for k, v in meta.get("declared_regions", {}).items()
                }
                raw_attr = meta.get("word_attribution", {})
                self.word_attribution = {int(k): v for k, v in raw_attr.items()}
            except Exception:
                pass

    def export_palace_state(self) -> Any:
        """Export Memory-Palace-style PalaceState (tools/geos_memory_palace_viz.py)."""
        if PalaceState is None or PalaceTile is None:
            return None

        tiles = []
        # Group into 16-word chunks per tile
        words_per_tile = 16
        total_tiles = (self.size_words + words_per_tile - 1) // words_per_tile
        grid_dim = int(np.ceil(np.sqrt(total_tiles)))

        for t_idx in range(total_tiles):
            start = t_idx * words_per_tile
            end = min(start + words_per_tile, self.size_words)
            chunk_words = self.get_words(start, end - start)
            chunk_bytes = json.dumps(chunk_words).encode()
            data_hash = hashlib.md5(chunk_bytes).hexdigest()

            # Determine modality: executable if written by loader/code, ecc/data otherwise
            chunk_writers = {
                self.word_attribution.get(w, {}).get("writer")
                for w in range(start, end)
                if w in self.word_attribution
            }
            if any(w in ("loader", "code") for w in chunk_writers):
                modality = "executable"
            elif chunk_writers:
                modality = "audio"
            else:
                modality = "empty"

            x = t_idx % grid_dim
            y = t_idx // grid_dim
            tile = PalaceTile(
                x=x,
                y=y,
                modality=modality,
                data_hash=data_hash,
                data={"words": chunk_words, "start_word": start},
                ecc_status="ok",
                has_audio=(modality == "audio"),
            )
            tiles.append(tile)

        return PalaceState(
            version="1.0",
            tiles=tiles,
            metadata={
                "size_words": self.size_words,
                "write_id": self.write_id_counter,
                "clobbers": len(self.clobbers),
            },
        )

    def export_palace_png(self, output_path: str) -> str:
        """Render to PNG using GeOSMemoryPalaceVisualizer."""
        if GeOSMemoryPalaceVisualizer is None:
            raise RuntimeError("GeOSMemoryPalaceVisualizer not available")
        state = self.export_palace_state()
        viz = GeOSMemoryPalaceVisualizer()
        return viz.render_to_png(state, output_path)


class SubstorWitness:
    """Witness that verifies substrate storage invariant gates.

    Asserts:
      (a) Zero clobbered words outside declared regions.
      (b) Writer attribution for every written word.
      (c) Survival across writeback: pre-writeback == post-writeback.
    """

    def __init__(self, surface_ram: SubstorSurfaceRAM):
        self.surface_ram = surface_ram

    def verify_zero_clobbers(self) -> None:
        """(a) Assert zero clobbered words outside writer's declared regions."""
        if len(self.surface_ram.clobbers) > 0 or len(self.surface_ram.clobbered_words) > 0:
            raise WitnessError(
                f"WITNESS_CLOBBER_DETECTED: {len(self.surface_ram.clobbers)} clobbered writes outside declared regions: {self.surface_ram.clobbers}"
            )
        # Double check all recorded attributions against declared regions
        for word, attr in self.surface_ram.word_attribution.items():
            writer = attr.get("writer")
            if not writer or not self.surface_ram.is_declared(writer, word):
                raise WitnessError(
                    f"WITNESS_CLOBBER_DETECTED: word {word} written by '{writer}' outside declared regions {self.surface_ram.declared_regions.get(writer, [])}"
                )

    def verify_attribution(self) -> Dict[str, Any]:
        """(b) Assert writer attribution for every written word."""
        if not self.surface_ram.word_attribution:
            raise WitnessError("WITNESS_ATTRIBUTION_EMPTY: No attributed writes found")

        for word, attr in self.surface_ram.word_attribution.items():
            if not attr:
                raise WitnessError(f"WITNESS_ATTRIBUTION_MISSING: Word {word} has no attribution record")
            writer = attr.get("writer")
            if not writer or writer == "unattributed":
                raise WitnessError(
                    f"WITNESS_ATTRIBUTION_MISSING: Word {word} has unattributed writer '{writer}'"
                )
            write_id = attr.get("write_id")
            if not isinstance(write_id, int) or write_id <= 0:
                raise WitnessError(
                    f"WITNESS_ATTRIBUTION_INVALID: Word {word} has invalid write_id '{write_id}'"
                )

        return {"verified": True, "count": len(self.surface_ram.word_attribution)}

    def verify_writeback_survival(
        self, pre_words: Sequence[int], post_words: Sequence[int]
    ) -> None:
        """(c) Assert memory image after writeback is byte-identical to pre-writeback image."""
        if len(pre_words) != len(post_words):
            raise WitnessError(
                f"WITNESS_DROPPED_WRITE: Pre-writeback count ({len(pre_words)}) != post-writeback count ({len(post_words)})"
            )

        mismatches = []
        for idx, (pre, post) in enumerate(zip(pre_words, post_words)):
            if (pre & 0xFFFFFFFF) != (post & 0xFFFFFFFF):
                mismatches.append((idx, hex(pre), hex(post)))

        if mismatches:
            raise WitnessError(
                f"WITNESS_DROPPED_WRITE: {len(mismatches)} words differed across writeback: {mismatches[:5]}"
            )

    def verify(
        self,
        pre_words: Optional[Sequence[int]] = None,
        post_words: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        """Run all substrate witness checks."""
        self.verify_zero_clobbers()
        attr_res = self.verify_attribution()
        if pre_words is not None and post_words is not None:
            self.verify_writeback_survival(pre_words, post_words)
        return {
            "status": "PASS",
            "clobbers": 0,
            "attribution_verified": attr_res.get("verified", True),
            "attributed_words": attr_res.get("count", 0),
        }


def verify_substrate_witness(
    surface_ram: SubstorSurfaceRAM,
    pre_words: Optional[Sequence[int]] = None,
    post_words: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """Top-level checker for substrate witness invariants."""
    witness = SubstorWitness(surface_ram)
    return witness.verify(pre_words, post_words)
