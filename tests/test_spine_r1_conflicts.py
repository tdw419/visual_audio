"""tests/test_spine_r1_conflicts.py — Gate for SPINE-R1 Phase 3 Step 6: WriteRegistry.conflicts().

Legs (5):
- L1 conflict found: write index directly with two entries sharing (origin_id, write_id)
  and distinct line_sha -> conflicts() returns exactly that key mapped to both shas.
- L2 'distinct' discriminator: two lines with same key and identical line_sha -> conflicts() == {}.
- L3 no false positives: healthy index built via register() (>=3 distinct keys) -> conflicts() == {}.
- L4 read-only: tree sha256 before/after conflicts() identical in L1 and L3 states;
  absent index -> {} without file or directory creation.
- L5 shape + multiplicity: two conflicting keys + one healthy key -> exactly the two
  conflicting keys reported, each with its 2 shas, healthy key absent, keys are (str, int).
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


def test_l1_conflict_found(tmp_path: Path) -> None:
    """L1 conflict found: two distinct records sharing (origin_id, write_id) are reported."""
    index_file = tmp_path / "spine_index.jsonl"

    rec1 = ArchiveRecord(
        write_id=42,
        writer="stage-a",
        image_path="out/kernel_a.npy",
        sidecar_path="out/surface_a.json",
        written_at="2026-09-12T10:00:00Z",
    )
    rec2 = ArchiveRecord(
        write_id=42,
        writer="stage-b",
        image_path="out/kernel_b.npy",
        sidecar_path="out/surface_b.json",
        written_at="2026-09-12T11:00:00Z",
    )
    sha1 = line_sha_for(rec1)
    sha2 = line_sha_for(rec2)
    assert sha1 != sha2

    entry1 = RegistryEntry(
        origin_id="tenant-alpha",
        write_id=42,
        writer=rec1.writer,
        image_path=rec1.image_path,
        line_sha=sha1,
        written_at=rec1.written_at,
    )
    entry2 = RegistryEntry(
        origin_id="tenant-alpha",
        write_id=42,
        writer=rec2.writer,
        image_path=rec2.image_path,
        line_sha=sha2,
        written_at=rec2.written_at,
    )

    # Write index directly, bypassing register()
    index_file.write_text(f"{entry_line(entry1)}\n{entry_line(entry2)}\n", encoding="utf-8")

    reg = WriteRegistry(index_path=str(index_file))
    conflicts = reg.conflicts()

    expected_key = ("tenant-alpha", 42)
    assert len(conflicts) == 1
    assert expected_key in conflicts
    assert isinstance(conflicts[expected_key], list)
    assert set(conflicts[expected_key]) == {sha1, sha2}
    assert conflicts[expected_key] == sorted([sha1, sha2])
    assert conflicts == {expected_key: sorted([sha1, sha2])}


def test_l2_distinct_discriminator(tmp_path: Path) -> None:
    """L2 'distinct' discriminator: identical line_sha with same key is not a conflict."""
    index_file = tmp_path / "spine_index.jsonl"

    rec = ArchiveRecord(
        write_id=10,
        writer="stage-a",
        image_path="out/img.npy",
        sidecar_path="out/s.json",
        written_at="2026-09-12T10:00:00Z",
    )
    sha = line_sha_for(rec)

    entry = RegistryEntry(
        origin_id="tenant-beta",
        write_id=10,
        writer=rec.writer,
        image_path=rec.image_path,
        line_sha=sha,
        written_at=rec.written_at,
    )

    line = entry_line(entry)
    # Two lines with identical key and identical line_sha
    index_file.write_text(f"{line}\n{line}\n", encoding="utf-8")

    reg = WriteRegistry(index_path=str(index_file))
    assert reg.conflicts() == {}

    # Even if other metadata differs, identical line_sha is not a conflict
    entry_variant = RegistryEntry(
        origin_id="tenant-beta",
        write_id=10,
        writer="other-writer",
        image_path="other-path",
        line_sha=sha,
        written_at="2026-09-12T11:00:00Z",
    )
    index_file.write_text(f"{line}\n{entry_line(entry_variant)}\n", encoding="utf-8")
    assert reg.conflicts() == {}


def test_l3_no_false_positives(tmp_path: Path) -> None:
    """L3 no false positives: healthy index built through register() reports no conflicts."""
    index_file = tmp_path / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    recs = [
        ArchiveRecord(1, "writer-a", "out/1.npy", "out/1.json", written_at="2026-09-12T10:00:00Z"),
        ArchiveRecord(2, "writer-a", "out/2.npy", "out/2.json", written_at="2026-09-12T10:00:01Z"),
        ArchiveRecord(3, "writer-b", "out/3.npy", "out/3.json", written_at="2026-09-12T10:00:02Z"),
        ArchiveRecord(1, "writer-c", "out/4.npy", "out/4.json", written_at="2026-09-12T10:00:03Z"),
    ]

    reg.register(recs[0], origin_id="origin-a")  # ("origin-a", 1)
    reg.register(recs[1], origin_id="origin-a")  # ("origin-a", 2)
    reg.register(recs[2], origin_id="origin-a")  # ("origin-a", 3)
    reg.register(recs[3], origin_id="origin-b")  # ("origin-b", 1)

    assert len(reg.entries) == 4
    conflicts = reg.conflicts()
    assert conflicts == {}


def test_l4_read_only(tmp_path: Path) -> None:
    """L4 read-only: tree sha256 unchanged across conflicts(), absent file returns {} cleanly."""
    # 4a: Absent index file
    absent_dir = tmp_path / "absent_tree"
    absent_file = absent_dir / "spine_index.jsonl"
    reg_absent = WriteRegistry(index_path=str(absent_file))

    assert not absent_file.exists()
    assert not absent_dir.exists()
    assert reg_absent.conflicts() == {}
    assert not absent_file.exists()
    assert not absent_dir.exists()
    assert reg_absent.entries == []

    # 4b: Read-only in L1 state (conflicted index on disk)
    l1_root = tmp_path / "l1_root"
    l1_root.mkdir()
    l1_index = l1_root / "spine_index.jsonl"

    rec1 = ArchiveRecord(1, "w1", "img1.npy", "s1.json")
    rec2 = ArchiveRecord(1, "w2", "img2.npy", "s2.json")
    e1 = RegistryEntry("org", 1, rec1.writer, rec1.image_path, line_sha_for(rec1))
    e2 = RegistryEntry("org", 1, rec2.writer, rec2.image_path, line_sha_for(rec2))
    l1_index.write_text(f"{entry_line(e1)}\n{entry_line(e2)}\n", encoding="utf-8")

    reg_l1 = WriteRegistry(index_path=str(l1_index))
    entries_before_l1 = list(reg_l1.entries)
    snap_before_l1 = _snapshot_tree(l1_root)

    res_l1 = reg_l1.conflicts()
    assert len(res_l1) == 1

    snap_after_l1 = _snapshot_tree(l1_root)
    assert snap_after_l1 == snap_before_l1
    assert reg_l1.entries == entries_before_l1

    # 4c: Read-only in L3 state (healthy index built through register)
    l3_root = tmp_path / "l3_root"
    l3_root.mkdir()
    l3_index = l3_root / "spine_index.jsonl"
    reg_l3 = WriteRegistry(index_path=str(l3_index))

    reg_l3.register(ArchiveRecord(1, "w", "i1.npy", "s1.json"), origin_id="org")
    reg_l3.register(ArchiveRecord(2, "w", "i2.npy", "s2.json"), origin_id="org")
    reg_l3.register(ArchiveRecord(3, "w", "i3.npy", "s3.json"), origin_id="org")

    entries_before_l3 = list(reg_l3.entries)
    snap_before_l3 = _snapshot_tree(l3_root)

    res_l3 = reg_l3.conflicts()
    assert res_l3 == {}

    snap_after_l3 = _snapshot_tree(l3_root)
    assert snap_after_l3 == snap_before_l3
    assert reg_l3.entries == entries_before_l3

    # 4d: Snapshot checker liveness control
    probe_file = l1_root / "probe.txt"
    probe_file.write_text("mutation-check")
    snap_mutated = _snapshot_tree(l1_root)
    assert snap_mutated != snap_after_l1


def test_l5_shape_and_multiplicity(tmp_path: Path) -> None:
    """L5 shape + multiplicity: two independent conflicts + healthy key are handled correctly."""
    index_file = tmp_path / "multi_index.jsonl"

    # Conflict 1 on key ("origin-x", 100)
    rec_x1 = ArchiveRecord(100, "wx1", "out/x1.npy", "out/x1.json", written_at="2026-09-12T01:00:00Z")
    rec_x2 = ArchiveRecord(100, "wx2", "out/x2.npy", "out/x2.json", written_at="2026-09-12T02:00:00Z")
    sha_x1 = line_sha_for(rec_x1)
    sha_x2 = line_sha_for(rec_x2)
    assert sha_x1 != sha_x2
    entry_x1 = RegistryEntry("origin-x", 100, rec_x1.writer, rec_x1.image_path, sha_x1, rec_x1.written_at)
    entry_x2 = RegistryEntry("origin-x", 100, rec_x2.writer, rec_x2.image_path, sha_x2, rec_x2.written_at)

    # Conflict 2 on key ("origin-y", 200)
    rec_y1 = ArchiveRecord(200, "wy1", "out/y1.npy", "out/y1.json", written_at="2026-09-12T03:00:00Z")
    rec_y2 = ArchiveRecord(200, "wy2", "out/y2.npy", "out/y2.json", written_at="2026-09-12T04:00:00Z")
    sha_y1 = line_sha_for(rec_y1)
    sha_y2 = line_sha_for(rec_y2)
    assert sha_y1 != sha_y2
    entry_y1 = RegistryEntry("origin-y", 200, rec_y1.writer, rec_y1.image_path, sha_y1, rec_y1.written_at)
    entry_y2 = RegistryEntry("origin-y", 200, rec_y2.writer, rec_y2.image_path, sha_y2, rec_y2.written_at)

    # Healthy key ("origin-z", 300)
    rec_z = ArchiveRecord(300, "wz", "out/z.npy", "out/z.json", written_at="2026-09-12T05:00:00Z")
    sha_z = line_sha_for(rec_z)
    entry_z = RegistryEntry("origin-z", 300, rec_z.writer, rec_z.image_path, sha_z, rec_z.written_at)

    # Lines also include a duplicate of entry_x1 to verify de-duplication
    lines = [
        entry_line(entry_x1),
        entry_line(entry_x2),
        entry_line(entry_x1),
        entry_line(entry_z),
        entry_line(entry_y1),
        entry_line(entry_y2),
    ]
    index_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    reg = WriteRegistry(index_path=str(index_file))
    conflicts = reg.conflicts()

    # Exactly the two conflicting keys reported
    expected_x = ("origin-x", 100)
    expected_y = ("origin-y", 200)
    assert set(conflicts.keys()) == {expected_x, expected_y}

    # Healthy key is absent
    assert ("origin-z", 300) not in conflicts

    # Keys are 2-tuples (str, int)
    for k in conflicts.keys():
        assert isinstance(k, tuple)
        assert len(k) == 2
        assert isinstance(k[0], str)
        assert isinstance(k[1], int)

    # Values are sorted and de-duplicated
    assert conflicts[expected_x] == sorted([sha_x1, sha_x2])
    assert conflicts[expected_y] == sorted([sha_y1, sha_y2])
    assert len(conflicts[expected_x]) == 2
    assert len(conflicts[expected_y]) == 2
