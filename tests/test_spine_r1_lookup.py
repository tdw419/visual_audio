"""tests/test_spine_r1_lookup.py — Gate for SPINE-R1 Phase 3 Step 7: WriteRegistry.lookup().

Legs (5):
- L1 hit round-trips: register() three records with distinct keys, then lookup(origin, write_id)
  for one of them returns exactly one RegistryEntry whose key, writer, image_path, line_sha,
  written_at equal the values returned by that register() call. No extra entries.
- L2 miss is []: an unregistered key on a populated index -> [] (a list, not None, not an exception).
- L3 absent index: a registry pointed at a path that does not exist -> [] for any key;
  afterwards the path still does not exist (no file, no parent directory created).
- L4 disk-truth (kills a self.entries-only implementation): register a key with instance A,
  then construct a fresh WriteRegistry(index_path=<same file>) with default (empty) entries
  and lookup() through that instance -> the entry is found.
- L5 read-only: sha256 snapshot of the whole temp tree (every file + the sorted directory list)
  is identical before/after a lookup() in both the L1 and L2 states, and self.entries is unchanged
  (same length and same key order) across the call.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.geos_archive import ArchiveRecord
from tools.geos_registry import (
    RegistryEntry,
    WriteRegistry,
    entry_line,
    line_sha_for,
    registry_key,
)


def _snapshot_tree(root: Path) -> Tuple[Dict[str, Tuple[str, int, int]], List[str]]:
    """Snapshot (relpath -> (sha256, size, st_mtime_ns)) and sorted directory list."""
    file_info: Dict[str, Tuple[str, int, int]] = {}
    dir_list: List[str] = []
    if not root.exists():
        return file_info, dir_list

    for dirpath, dirnames, filenames in os.walk(str(root)):
        for d in dirnames:
            full_d = os.path.join(dirpath, d)
            dir_list.append(os.path.relpath(full_d, str(root)))
        for f in filenames:
            full_f = os.path.join(dirpath, f)
            rel = os.path.relpath(full_f, str(root))
            st = os.stat(full_f)
            data = Path(full_f).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            file_info[rel] = (digest, st.st_size, st.st_mtime_ns)
    dir_list.sort()
    return file_info, dir_list


def test_l1_hit_round_trips(tmp_path: Path) -> None:
    """L1 hit round-trips: register() three records with distinct keys,

    then lookup(origin, write_id) for one returns exactly one RegistryEntry
    whose key, writer, image_path, line_sha, written_at match the registered record.
    """
    index_file = tmp_path / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec1 = ArchiveRecord(
        write_id=1,
        writer="writer-a",
        image_path="out/kernel_1.npy",
        sidecar_path="out/surface_1.json",
        written_at="2026-09-12T10:00:00Z",
    )
    rec2 = ArchiveRecord(
        write_id=2,
        writer="writer-b",
        image_path="out/kernel_2.npy",
        sidecar_path="out/surface_2.json",
        written_at="2026-09-12T10:00:01Z",
    )
    rec3 = ArchiveRecord(
        write_id=1,
        writer="writer-c",
        image_path="out/kernel_3.npy",
        sidecar_path="out/surface_3.json",
        written_at="2026-09-12T10:00:02Z",
    )

    e1 = reg.register(rec1, origin_id="origin-alpha")
    e2 = reg.register(rec2, origin_id="origin-alpha")
    e3 = reg.register(rec3, origin_id="origin-beta")

    assert len({e1.key, e2.key, e3.key}) == 3

    # lookup for one of them returns exactly one RegistryEntry with matching fields
    results = reg.lookup("origin-alpha", 2)
    assert isinstance(results, list)
    assert len(results) == 1
    found = results[0]

    assert isinstance(found, RegistryEntry)
    assert found.key == e2.key == registry_key("origin-alpha", 2)
    assert found.origin_id == e2.origin_id == "origin-alpha"
    assert found.write_id == e2.write_id == 2
    assert found.writer == e2.writer == "writer-b"
    assert found.image_path == e2.image_path == "out/kernel_2.npy"
    assert found.line_sha == e2.line_sha == line_sha_for(rec2)
    assert found.written_at == e2.written_at == "2026-09-12T10:00:01Z"
    assert found == e2

    # Verify other registered entries also round-trip with no extra entries
    res1 = reg.lookup("origin-alpha", 1)
    assert len(res1) == 1
    assert res1[0] == e1

    res3 = reg.lookup("origin-beta", 1)
    assert len(res3) == 1
    assert res3[0] == e3


def test_l2_miss_is_empty_list(tmp_path: Path) -> None:
    """L2 miss is []: an unregistered key on a populated index -> []."""
    index_file = tmp_path / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec = ArchiveRecord(
        write_id=1,
        writer="writer-a",
        image_path="out/kernel_1.npy",
        sidecar_path="out/surface_1.json",
        written_at="2026-09-12T10:00:00Z",
    )
    reg.register(rec, origin_id="origin-alpha")

    # Unregistered origin_id
    res_miss_origin = reg.lookup("origin-nonexistent", 1)
    assert res_miss_origin == []
    assert isinstance(res_miss_origin, list)

    # Unregistered write_id
    res_miss_write_id = reg.lookup("origin-alpha", 999)
    assert res_miss_write_id == []
    assert isinstance(res_miss_write_id, list)

    # Unregistered origin and write_id
    res_miss_both = reg.lookup("origin-gamma", 42)
    assert res_miss_both == []
    assert isinstance(res_miss_both, list)


def test_l3_absent_index(tmp_path: Path) -> None:
    """L3 absent index: registry pointed at nonexistent path -> [] without creating path or dir."""
    nonexistent_dir = tmp_path / "does" / "not" / "exist"
    absent_index = nonexistent_dir / "spine_index.jsonl"

    assert not absent_index.exists()
    assert not nonexistent_dir.exists()

    reg = WriteRegistry(index_path=str(absent_index))

    res1 = reg.lookup("any-origin", 1)
    assert res1 == []
    assert isinstance(res1, list)

    res2 = reg.lookup("another-origin", 999)
    assert res2 == []
    assert isinstance(res2, list)

    # Afterwards the path still does not exist (no file, no parent directory created)
    assert not absent_index.exists()
    assert not nonexistent_dir.exists()


def test_l4_disk_truth(tmp_path: Path) -> None:
    """L4 disk-truth: fresh WriteRegistry with empty entries finds writes persisted by instance A."""
    index_file = tmp_path / "spine_index.jsonl"
    reg_a = WriteRegistry(index_path=str(index_file))

    rec = ArchiveRecord(
        write_id=42,
        writer="writer-truth",
        image_path="out/truth.npy",
        sidecar_path="out/truth.json",
        written_at="2026-09-12T11:00:00Z",
    )
    entry_a = reg_a.register(rec, origin_id="origin-truth")

    # Construct a fresh WriteRegistry on the same file with default (empty) entries
    reg_b = WriteRegistry(index_path=str(index_file))
    assert reg_b.entries == []

    # lookup() through instance B finds the entry on disk
    results_b = reg_b.lookup("origin-truth", 42)
    assert isinstance(results_b, list)
    assert len(results_b) == 1
    found_b = results_b[0]

    assert found_b.key == entry_a.key == registry_key("origin-truth", 42)
    assert found_b.origin_id == entry_a.origin_id
    assert found_b.write_id == entry_a.write_id
    assert found_b.writer == entry_a.writer
    assert found_b.image_path == entry_a.image_path
    assert found_b.line_sha == entry_a.line_sha == line_sha_for(rec)
    assert found_b.written_at == entry_a.written_at
    assert found_b == entry_a

    # reg_b.entries remains unchanged
    assert reg_b.entries == []


def test_l5_read_only(tmp_path: Path) -> None:
    """L5 read-only: tree snapshot and self.entries are identical before/after lookup (hit and miss)."""
    root = tmp_path / "registry_root"
    root.mkdir()
    index_file = root / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec1 = ArchiveRecord(
        write_id=1,
        writer="w1",
        image_path="out/1.npy",
        sidecar_path="out/1.json",
        written_at="2026-09-12T10:00:00Z",
    )
    rec2 = ArchiveRecord(
        write_id=2,
        writer="w2",
        image_path="out/2.npy",
        sidecar_path="out/2.json",
        written_at="2026-09-12T10:00:01Z",
    )
    reg.register(rec1, origin_id="org")
    reg.register(rec2, origin_id="org")

    # 5a: Snapshot before/after lookup in L1 state (hit)
    entries_before_hit = list(reg.entries)
    snap_before_hit = _snapshot_tree(root)

    hit_res = reg.lookup("org", 1)
    assert len(hit_res) == 1

    snap_after_hit = _snapshot_tree(root)
    assert snap_after_hit == snap_before_hit
    assert reg.entries == entries_before_hit
    assert len(reg.entries) == len(entries_before_hit)
    assert [e.key for e in reg.entries] == [e.key for e in entries_before_hit]

    # 5b: Snapshot before/after lookup in L2 state (miss)
    entries_before_miss = list(reg.entries)
    snap_before_miss = _snapshot_tree(root)

    miss_res = reg.lookup("org", 999)
    assert miss_res == []

    snap_after_miss = _snapshot_tree(root)
    assert snap_after_miss == snap_before_miss
    assert reg.entries == entries_before_miss
    assert len(reg.entries) == len(entries_before_miss)
    assert [e.key for e in reg.entries] == [e.key for e in entries_before_miss]

    # 5c: Liveness check on snapshot detector
    probe_file = root / "mutation_probe.txt"
    probe_file.write_text("detect-mutation", encoding="utf-8")
    snap_mutated = _snapshot_tree(root)
    assert snap_mutated != snap_after_miss
