#!/usr/bin/env python3
"""
geos_registry — global cross-directory write registry (Glyph OS spine, SKELETON).

PROBLEM (ruling 2026-09-12 §Reserved item 3, second named spine item):
    Write identity (write_id, writer) is recorded per-publish in a sidecar
    NEXT TO the image. There is no global index, so:
      - you cannot answer "which write produced this artifact?" from outside
        the directory the artifact happens to live in;
      - you cannot detect write_id collisions across directories (two
        independent emitters both start at write_id 1);
      - retention (geos_archive) cannot refuse to evict a record another
        directory still references.

PURPOSE OF THIS MODULE
    One append-only, cross-directory index of publish events, keyed by a
    globally unambiguous identity. The RECORD SHAPE and its canonical
    serialisation are implemented (deterministic utilities). The SCAN and
    QUERY surfaces are stubbed for the builder's fill-in pass.

DESIGN INVARIANTS
    I1  Append-only. The index is a JSONL log; entries are never rewritten in
        place. Compaction, if ever added, must be an explicit, gated operation.
    I2  Globally unambiguous key. write_id alone is NOT unique across
        directories (each emitter counts from its own start), so the key is
        the pair (origin_id, write_id). origin_id names the publish root.
    I3  Canonical bytes. Every line is serialised by geos_archive.
        canonical_record_line() with sorted keys; identical events produce
        identical lines so the index has a stable md5 (receipt discipline).
    I4  Read-only queries. lookup()/conflicts() must never mutate the log.

BOUNDARY MAP
    geos_emit.publish() --> sidecar (write_id, writer)
                                |
                                v
    +----------------------------------------------------------+
    | geos_registry: WriteRegistry                              |
    |   register(record, origin_id)   [STUB: append to index]   |
    |   lookup(origin_id, write_id)   [STUB: read-only scan]    |
    |   conflicts()                   [STUB: duplicate-key scan]|
    |   key(origin_id, write_id)      [IMPLEMENTED: pure]       |
    +----------------------------------------------------------+
                                ^
                                |  retention refuses to evict a
                                |  still-referenced record
                        geos_archive.ArchiveStore.compact()

PHASE STATUS
    Phase 1 (structure) : done — compiles, stdlib-only, no third-party imports.
    Phase 2 (lock)      : done — invariants + intent comments.
    Phase 3 (population): TODO — append/scan/lookup bodies; see
                          systems/GLYPH_SPINE_SKELETON.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.geos_archive import ArchiveRecord, canonical_record_line, parse_record

__all__ = ["RegistryEntry", "WriteRegistry", "registry_key", "entry_line", "index_digest"]


@dataclass(frozen=True)
class RegistryEntry:
    """One indexed publish event.

    key      : (origin_id, write_id) — globally unambiguous (I2).
    line_sha : sha256 of the canonical record line, so the index can be
               verified without re-reading every sidecar.
    """

    origin_id: str
    write_id: int
    writer: str
    image_path: str
    line_sha: str
    written_at: str = ""

    @property
    def key(self) -> Tuple[str, int]:
        return (self.origin_id, self.write_id)


def registry_key(origin_id: str, write_id: int) -> Tuple[str, int]:
    """Global key for a publish event. IMPLEMENTED (pure).

    origin_id must be a non-empty string; failing loudly here is the point —
    an origin-less entry would silently recreate the collision this module
    exists to prevent.
    """
    if not isinstance(origin_id, str) or not origin_id.strip():
        raise ValueError("origin_id must be a non-empty string (global key component)")
    if not isinstance(write_id, int):
        raise TypeError(f"write_id must be an int, got {type(write_id).__name__}")
    return (origin_id.strip(), write_id)


def entry_line(entry: RegistryEntry) -> str:
    """Canonical JSONL line for an index entry. IMPLEMENTED (deterministic).

    Reuses the record serialiser's discipline (sorted keys, compact
    separators) so index bytes are stable across runs (I3).
    """
    payload: Dict[str, Any] = {
        "image_path": entry.image_path,
        "line_sha": entry.line_sha,
        "origin_id": entry.origin_id,
        "write_id": entry.write_id,
        "writer": entry.writer,
        "written_at": entry.written_at,
    }
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def index_digest(lines: Sequence[str]) -> str:
    """sha256 over the ordered index lines. IMPLEMENTED (pure).

    The digest is the index's receipt: it must change when the log changes
    and stay identical when it does not.
    """
    h = hashlib.sha256()
    for line in lines:
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def line_sha_for(record: ArchiveRecord) -> str:
    """sha256 of a record's canonical line. IMPLEMENTED (pure)."""
    return hashlib.sha256(canonical_record_line(record).encode("utf-8")).hexdigest()


def _scan_disk_for_key(index_path: str, key: Tuple[str, int]) -> Optional[int]:
    """Scan existing index file on disk for a registry key.

    Returns the 1-based line number if found, or None if the key is absent
    or the file does not exist. Blank lines are skipped.
    """
    if not os.path.exists(index_path):
        return None
    with open(index_path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            data = json.loads(line)
            if isinstance(data, dict) and (data.get("origin_id"), data.get("write_id")) == key:
                return lineno
    return None


@dataclass
class WriteRegistry:
    """Append-only cross-directory index of publish events.

    PHASE 3 TODO (builder) — bodies are stubs on purpose:
        register()  : append entry_line() to index_path. Must be append-only
                      (open "a"), must fsync-or-refuse, must reject a duplicate
                      key rather than rewriting history (I1 + I2).
        lookup()    : read-only scan; returns [] on miss — a miss is not an
                      error, but lookup() must never fabricate an entry.
        conflicts() : groups entries by registry_key(); returns keys with
                      >1 distinct line_sha (same key, different content =
                      the case retention must refuse to evict through).
        scan()      : discover sidecars under a root and yield ArchiveRecords
                      for registration. Read-only; no side effects on the
                      scanned tree.
    """

    index_path: str
    entries: List[RegistryEntry] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.entries is None:
            self.entries = []

    def register(self, record: ArchiveRecord, origin_id: str) -> RegistryEntry:
        """Append one canonical line to the append-only index and return the entry.

        Refuses any duplicate (origin_id, write_id) key, regardless of line_sha,
        before writing to disk (R2). This is deliberately stricter than conflicts()'s
        rule (>1 distinct line_sha): a registry key is a unique publish identity,
        so a second registration of the same key is never legitimate (I1/I2).
        """
        key = registry_key(origin_id, record.write_id)
        entry = RegistryEntry(
            origin_id=key[0],
            write_id=key[1],
            writer=record.writer,
            image_path=record.image_path,
            line_sha=line_sha_for(record),
            written_at=record.written_at,
        )

        # Duplicate-key refusal happens BEFORE any byte is written (R2).
        line_on_disk = _scan_disk_for_key(self.index_path, key)
        if line_on_disk is not None:
            raise ValueError(
                f"refusing to register: duplicate registry key {key!r} already present at line {line_on_disk} of {self.index_path} (append-only index: history is never rewritten)"
            )

        for entry_item in self.entries:
            if entry_item.key == key:
                raise ValueError(
                    f"refusing to register: duplicate registry key {key!r} already present at line 0 of {self.index_path} (append-only index: history is never rewritten)"
                )

        # Append semantics (R3): create parent directory if needed, write one full line, flush, fsync.
        line_to_write = entry_line(entry) + "\n"
        parent = os.path.dirname(self.index_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(line_to_write)
            f.flush()
            os.fsync(f.fileno())

        self.entries.append(entry)
        return entry

    def lookup(self, origin_id: str, write_id: int) -> List[RegistryEntry]:
        """Read-only scan of the persisted index for (origin_id, write_id).

        Returns [] on miss (key absent, empty index, absent file).
        Never fabricates an entry. Read-only: does not write, does not mutate self.entries.
        """
        try:
            target_key = registry_key(origin_id, write_id)
        except (ValueError, TypeError):
            return []

        if not os.path.exists(self.index_path) or not os.path.isfile(self.index_path):
            return []

        matches: List[RegistryEntry] = []
        with open(self.index_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue

                if (data.get("origin_id"), data.get("write_id")) != target_key:
                    continue

                writer = data.get("writer")
                image_path = data.get("image_path")
                line_sha = data.get("line_sha")
                written_at = data.get("written_at", "")

                if not isinstance(writer, str) or not isinstance(image_path, str) or not isinstance(line_sha, str):
                    continue
                if not line_sha:
                    continue
                if written_at is None:
                    written_at = ""
                elif not isinstance(written_at, str):
                    continue

                matches.append(
                    RegistryEntry(
                        origin_id=target_key[0],
                        write_id=target_key[1],
                        writer=writer,
                        image_path=image_path,
                        line_sha=line_sha,
                        written_at=written_at,
                    )
                )

        return matches

    def conflicts(self) -> Dict[Tuple[str, int], List[str]]:
        """Return keys mapping to >1 distinct line_sha.

        Reads the persisted append-only index at self.index_path.
        A miss (absent file) returns {} without error or side-effect.
        Read-only: does not write, does not mutate self.entries.
        """
        if not os.path.exists(self.index_path) or not os.path.isfile(self.index_path):
            return {}

        key_shas: Dict[Tuple[str, int], set[str]] = {}
        with open(self.index_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue

                origin_id = data.get("origin_id")
                write_id = data.get("write_id")
                line_sha = data.get("line_sha")

                if not isinstance(origin_id, str) or type(write_id) is not int or not isinstance(line_sha, str):
                    continue
                try:
                    key = registry_key(origin_id, write_id)
                except (ValueError, TypeError):
                    continue
                if not line_sha:
                    continue

                if key not in key_shas:
                    key_shas[key] = set()
                key_shas[key].add(line_sha)

        conflicts_found: Dict[Tuple[str, int], List[str]] = {}
        for key in sorted(key_shas.keys()):
            shas = key_shas[key]
            if len(shas) > 1:
                conflicts_found[key] = sorted(shas)

        return conflicts_found

    def scan(self, root: str) -> List[ArchiveRecord]:
        """Discover attributable (image, sidecar) pairs under root.

        Mirrors ArchiveStore.plan()'s walk verbatim (S1).
        Sorted by (write_id, image_path) (S2).
        Negative space (nonexistent, regular file, empty dir) returns [] (S3).
        Read-only: no mutations, does not touch self.index_path or self.entries (S4).
        Paths are joins, not normalisations (S5).
        """
        if not os.path.exists(root) or not os.path.isdir(root):
            return []

        records: List[ArchiveRecord] = []

        for dirpath, dirs, files in os.walk(root):
            dirs.sort()
            files.sort()

            images = [f for f in files if f.endswith(".npy") or f.endswith(".png")]
            claimed_sidecars: set[str] = set()

            for img in images:
                image_path = os.path.join(dirpath, img)
                stem, _ = os.path.splitext(img)

                sidecar_candidates = ["surface.meta.json", f"{stem}.meta.json"]
                chosen_sidecar: Optional[str] = None
                for cand in sidecar_candidates:
                    if cand in files and cand not in claimed_sidecars:
                        chosen_sidecar = cand
                        break

                if chosen_sidecar is None:
                    continue

                claimed_sidecars.add(chosen_sidecar)
                sidecar_path = os.path.join(dirpath, chosen_sidecar)

                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f:
                        sidecar_dict = json.load(f)
                    rec = parse_record(sidecar_dict, image_path=image_path, sidecar_path=sidecar_path)
                    records.append(rec)
                except (ValueError, TypeError, json.JSONDecodeError, OSError):
                    continue

        return sorted(records, key=lambda r: (r.write_id, r.image_path))

    def lines(self) -> List[str]:
        """Canonical lines for the in-memory entries (IMPLEMENTED, pure)."""
        return [entry_line(e) for e in self.entries]

    def digest(self) -> str:
        """Index digest over current entries (IMPLEMENTED, pure)."""
        return index_digest(self.lines())


if __name__ == "__main__":  # Phase-1 smoke check: shape, not behaviour.
    reg = WriteRegistry(index_path="/tmp/glyph_spine_index.jsonl")
    rec = ArchiveRecord(7, "stage-a", "out/kernel_memory.npy", "out/surface.meta.json", bytes_len=4096)
    entry = reg.register(rec, origin_id="visual_audio/output")
    print(f"key={entry.key} line_sha={entry.line_sha[:16]}...")
    print(f"index_digest={reg.digest()[:16]}...")
