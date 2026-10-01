"""tests/test_spine_r1_scan.py — Gate for SPINE-R1 Phase 3 Step 5: WriteRegistry.scan(root).

Legs (8):
- L1 discovery basics — temp root with 3 pairs (surface.meta.json): scan() returns 3 ArchiveRecords
  with exact write_id / writer / image_path / sidecar_path / bytes_len / written_at from the sidecars.
- L2 read-only proof (S6, BINDING) — recursive sha256 snapshot before vs after scan() identical:
  same relpath set, same sha256, same size, same st_mtime_ns, same dir set; no new file appears anywhere under root.
- L3 snapshot liveness control — the same snapshot function run around a deliberate write reports a difference
  (non-vacuous checker).
- L4 skip, not crash — image with no sidecar skipped; sidecar with no write_id skipped; malformed-JSON
  sidecar skipped; nonexistent root []; root-is-a-file []; empty dir [] — and in every case a sibling
  valid pair is still returned.
- L5 pairing rule — <stem>.meta.json fallback when no surface.meta.json; surface.meta.json preferred
  when both exist; one sidecar claimed by at most one image (two images whose stem collides -> exactly one record).
- L6 determinism — two scans of the same tree are list-equal (order included); a scan after unrelated
  register() calls on the same instance is unchanged.
- L7 no side effects outside root — scan() does not create self.index_path (assert not os.path.exists(...))
  even when its parent dir does not exist, and leaves self.entries unchanged.
- L8 anti-drift equivalence — on one fixture tree, the record set from scan(root) equals the record set
  ArchiveStore(root).plan(RetentionPolicy(keep_total=0)) condemns. Measured in a scratch probe:
  RetentionPolicy(keep_total=0) evicts all survivors under global count cap pass 3 (REASON_OVER_COUNT).
  Compared as sets of (write_id, writer, image_path, sidecar_path, bytes_len, written_at).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.geos_archive import ArchiveRecord, ArchiveStore, RetentionPolicy
from tools.geos_registry import RegistryEntry, WriteRegistry


def _snapshot_tree(root: Path) -> Tuple[Dict[str, Tuple[str, int, int]], List[str]]:
    """Snapshot (relpath -> (sha256, size, st_mtime_ns)) and sorted directory list."""
    file_info: Dict[str, Tuple[str, int, int]] = {}
    dir_list: List[str] = []
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


def test_l1_discovery_basics(tmp_path: Path) -> None:
    """L1: discovery basics — temp root with 3 pairs returns 3 ArchiveRecords with exact fields."""
    root = tmp_path / "scan_root"
    root.mkdir(parents=True, exist_ok=True)

    d1 = root / "dir1"
    d1.mkdir()
    img1 = d1 / "kernel.npy"
    img1.write_bytes(b"\x01" * 120)
    s1 = d1 / "surface.meta.json"
    s1.write_text(
        json.dumps(
            {
                "write_id": 10,
                "writer": "stage-a",
                "bytes_len": 120,
                "written_at": "2026-09-12T10:00:00Z",
            }
        )
    )

    d2 = root / "dir2"
    d2.mkdir()
    img2 = d2 / "render.png"
    img2.write_bytes(b"\x02" * 240)
    s2 = d2 / "surface.meta.json"
    s2.write_text(
        json.dumps(
            {
                "write_id": 20,
                "writer": "stage-b",
                "bytes_len": 240,
                "written_at": "2026-09-12T10:00:01Z",
            }
        )
    )

    d3 = root / "sub" / "dir3"
    d3.mkdir(parents=True)
    img3 = d3 / "patch.npy"
    img3.write_bytes(b"\x03" * 360)
    s3 = d3 / "surface.meta.json"
    s3.write_text(
        json.dumps(
            {
                "write_id": 30,
                "writer": "stage-c",
                "bytes_len": 360,
                "written_at": "2026-09-12T10:00:02Z",
            }
        )
    )

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"))
    records = reg.scan(str(root))

    assert len(records) == 3

    assert records[0] == ArchiveRecord(
        write_id=10,
        writer="stage-a",
        image_path=str(img1),
        sidecar_path=str(s1),
        bytes_len=120,
        written_at="2026-09-12T10:00:00Z",
    )
    assert records[1] == ArchiveRecord(
        write_id=20,
        writer="stage-b",
        image_path=str(img2),
        sidecar_path=str(s2),
        bytes_len=240,
        written_at="2026-09-12T10:00:01Z",
    )
    assert records[2] == ArchiveRecord(
        write_id=30,
        writer="stage-c",
        image_path=str(img3),
        sidecar_path=str(s3),
        bytes_len=360,
        written_at="2026-09-12T10:00:02Z",
    )


def test_l2_readonly_proof(tmp_path: Path) -> None:
    """L2: read-only proof (S6, BINDING) — sha256 tree snapshot identical before and after scan()."""
    root = tmp_path / "ro_root"
    root.mkdir(parents=True, exist_ok=True)

    d1 = root / "pair1"
    d1.mkdir()
    (d1 / "image.npy").write_bytes(b"\xaa" * 64)
    (d1 / "surface.meta.json").write_text(
        json.dumps({"write_id": 1, "writer": "w1", "bytes_len": 64, "written_at": "2026-09-12T11:00:00Z"})
    )

    d2 = root / "nested" / "pair2"
    d2.mkdir(parents=True)
    (d2 / "view.png").write_bytes(b"\xbb" * 128)
    (d2 / "view.meta.json").write_text(
        json.dumps({"write_id": 2, "writer": "w2", "bytes_len": 128, "written_at": "2026-09-12T11:00:01Z"})
    )

    snap_before = _snapshot_tree(root)

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"))
    _ = reg.scan(str(root))

    snap_after = _snapshot_tree(root)

    assert snap_before == snap_after

    files_before, dirs_before = snap_before
    files_after, dirs_after = snap_after
    assert set(files_before.keys()) == set(files_after.keys())
    assert dirs_before == dirs_after
    for rel, (digest, size, mtime) in files_before.items():
        after_digest, after_size, after_mtime = files_after[rel]
        assert digest == after_digest
        assert size == after_size
        assert mtime == after_mtime


def test_l3_snapshot_liveness_control(tmp_path: Path) -> None:
    """L3: snapshot liveness control — snapshot function detects mutations (non-vacuous checker)."""
    root = tmp_path / "live_root"
    root.mkdir(parents=True, exist_ok=True)
    f1 = root / "file1.txt"
    f1.write_text("initial content")

    snap1 = _snapshot_tree(root)

    # 1. Writing a new file must be detected
    f2 = root / "file2.txt"
    f2.write_text("second content")
    snap2 = _snapshot_tree(root)
    assert snap1 != snap2
    assert set(snap2[0].keys()) - set(snap1[0].keys()) == {"file2.txt"}

    # 2. Modifying bytes of an existing file must be detected
    f1.write_text("mutated content")
    snap3 = _snapshot_tree(root)
    assert snap2 != snap3
    assert snap2[0]["file1.txt"][0] != snap3[0]["file1.txt"][0]  # sha256 changed

    # 3. Adding a new directory must be detected
    new_dir = root / "new_folder"
    new_dir.mkdir()
    snap4 = _snapshot_tree(root)
    assert snap3 != snap4
    assert "new_folder" in snap4[1]
    assert "new_folder" not in snap3[1]


def test_l4_skip_not_crash(tmp_path: Path) -> None:
    """L4: skip, not crash — skips orphan image, bad/malformed sidecars; negative roots return []."""
    root = tmp_path / "robust_root"
    root.mkdir(parents=True, exist_ok=True)

    # Orphan image (no sidecar)
    d_orphan = root / "orphan"
    d_orphan.mkdir()
    (d_orphan / "orphan.npy").write_bytes(b"\x00" * 32)

    # Bad sidecar (valid JSON, but missing write_id)
    d_no_id = root / "no_write_id"
    d_no_id.mkdir()
    (d_no_id / "data.npy").write_bytes(b"\x00" * 32)
    (d_no_id / "surface.meta.json").write_text(json.dumps({"writer": "w", "bytes_len": 32}))

    # Malformed JSON sidecar
    d_malformed = root / "malformed"
    d_malformed.mkdir()
    (d_malformed / "corrupt.png").write_bytes(b"\x00" * 32)
    (d_malformed / "surface.meta.json").write_text("{this is not valid json")

    # Sibling valid pair
    d_valid = root / "valid"
    d_valid.mkdir()
    valid_img = d_valid / "good.npy"
    valid_img.write_bytes(b"\x00" * 64)
    valid_sc = d_valid / "surface.meta.json"
    valid_sc.write_text(
        json.dumps({"write_id": 99, "writer": "survivor", "bytes_len": 64, "written_at": "2026-09-12T12:00:00Z"})
    )

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"))

    # Sibling valid pair is discovered despite corrupt / orphan neighbors
    records = reg.scan(str(root))
    assert len(records) == 1
    assert records[0].write_id == 99
    assert records[0].writer == "survivor"
    assert records[0].image_path == str(valid_img)
    assert records[0].sidecar_path == str(valid_sc)

    # Negative space cases:
    # 1. Nonexistent root -> []
    assert reg.scan(str(tmp_path / "nonexistent_dir")) == []

    # 2. Root is a regular file -> []
    reg_file = tmp_path / "regular_file.txt"
    reg_file.write_text("plain text")
    assert reg.scan(str(reg_file)) == []

    # 3. Empty directory -> []
    empty_d = tmp_path / "empty_dir"
    empty_d.mkdir()
    assert reg.scan(str(empty_d)) == []


def test_l5_pairing_rule(tmp_path: Path) -> None:
    """L5: pairing rule — <stem>.meta.json fallback, surface.meta.json preference, single sidecar claim."""
    root = tmp_path / "pairing_root"
    root.mkdir(parents=True, exist_ok=True)

    # Case 1: <stem>.meta.json fallback when surface.meta.json absent
    d1 = root / "fallback"
    d1.mkdir()
    img_fb = d1 / "frame_fb.npy"
    img_fb.write_bytes(b"\x00" * 50)
    sc_fb = d1 / "frame_fb.meta.json"
    sc_fb.write_text(json.dumps({"write_id": 101, "writer": "fb", "bytes_len": 50}))

    # Case 2: surface.meta.json preferred over <stem>.meta.json when both exist
    d2 = root / "prefer"
    d2.mkdir()
    img_pref = d2 / "view.png"
    img_pref.write_bytes(b"\x00" * 60)
    sc_surface = d2 / "surface.meta.json"
    sc_surface.write_text(json.dumps({"write_id": 102, "writer": "surface_pref", "bytes_len": 60}))
    sc_stem = d2 / "view.meta.json"
    sc_stem.write_text(json.dumps({"write_id": 999, "writer": "stem_ignored", "bytes_len": 60}))

    # Case 3: Two images whose stem collides -> sidecar claimed by at most one image (exactly 1 record)
    d3 = root / "collide"
    d3.mkdir()
    img_c1 = d3 / "collide.npy"
    img_c1.write_bytes(b"\x00" * 70)
    img_c2 = d3 / "collide.png"
    img_c2.write_bytes(b"\x00" * 70)
    sc_c = d3 / "collide.meta.json"
    sc_c.write_text(json.dumps({"write_id": 103, "writer": "collide_single", "bytes_len": 70}))

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"))
    records = reg.scan(str(root))

    assert len(records) == 3

    # Check fallback
    r_fb = next(r for r in records if r.write_id == 101)
    assert r_fb.image_path == str(img_fb)
    assert r_fb.sidecar_path == str(sc_fb)

    # Check preference for surface.meta.json
    r_pref = next(r for r in records if r.write_id == 102)
    assert r_pref.image_path == str(img_pref)
    assert r_pref.sidecar_path == str(sc_surface)
    assert r_pref.writer == "surface_pref"

    # Check collide: only collide.npy claimed collide.meta.json; collide.png had no sidecar left
    r_collide = next(r for r in records if r.write_id == 103)
    assert r_collide.image_path == str(img_c1)
    assert r_collide.sidecar_path == str(sc_c)


def test_l6_determinism(tmp_path: Path) -> None:
    """L6: determinism — identical order across scans; unaffected by unrelated register() calls."""
    root = tmp_path / "det_root"
    root.mkdir(parents=True, exist_ok=True)

    # Create several pairs out of order
    pairs_data = [
        (40, "dir_40", "b.npy"),
        (10, "dir_10", "a.png"),
        (30, "dir_30", "c.npy"),
        (20, "dir_20", "d.png"),
    ]
    for wid, dirname, imgname in pairs_data:
        d = root / dirname
        d.mkdir()
        (d / imgname).write_bytes(b"\x00" * 10)
        (d / "surface.meta.json").write_text(json.dumps({"write_id": wid, "writer": f"writer_{wid}"}))

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"))

    scan1 = reg.scan(str(root))
    scan2 = reg.scan(str(root))
    assert scan1 == scan2
    assert [r.write_id for r in scan1] == [10, 20, 30, 40]

    # Perform unrelated register() call on same instance
    unrelated_rec = ArchiveRecord(
        write_id=999,
        writer="unrelated",
        image_path="/tmp/unrelated.npy",
        sidecar_path="/tmp/unrelated.json",
    )
    reg.register(unrelated_rec, origin_id="origin-unrelated")

    scan3 = reg.scan(str(root))
    assert scan3 == scan1


def test_l7_no_side_effects_outside_root(tmp_path: Path) -> None:
    """L7: no side effects outside root — does not create index_path or its parent, leaves entries unchanged."""
    absent_parent = tmp_path / "nonexistent_parent" / "nested"
    absent_index = absent_parent / "spine_index.jsonl"
    assert not absent_parent.exists()
    assert not absent_index.exists()

    reg = WriteRegistry(index_path=str(absent_index))
    assert reg.entries == []

    # Valid tree to scan
    root = tmp_path / "valid_tree"
    root.mkdir()
    (root / "img.npy").write_bytes(b"\x00" * 10)
    (root / "surface.meta.json").write_text(json.dumps({"write_id": 5, "writer": "w5"}))

    recs = reg.scan(str(root))
    assert len(recs) == 1

    # index_path and parent directory must NOT be created
    assert not absent_parent.exists()
    assert not absent_index.exists()
    assert reg.entries == []

    # If reg.entries already had items, they must remain untouched
    dummy_entry = RegistryEntry(
        origin_id="org",
        write_id=1,
        writer="w",
        image_path="img.npy",
        line_sha="abc",
    )
    reg.entries.append(dummy_entry)

    recs2 = reg.scan(str(root))
    assert len(recs2) == 1
    assert reg.entries == [dummy_entry]
    assert not absent_index.exists()


def test_l8_antidrift_equivalence(tmp_path: Path) -> None:
    """L8: anti-drift equivalence — scan(root) equals ArchiveStore.plan(keep_total=0) condemned record set.

    Note on policy: RetentionPolicy(keep_total=0) was verified via probe to condemn 100% of discovered
    records under global count cap pass 3 (REASON_OVER_COUNT).
    """
    root = tmp_path / "fixture_tree"
    root.mkdir(parents=True, exist_ok=True)

    # 1. Valid surface.meta.json pair
    d1 = root / "p1"
    d1.mkdir()
    (d1 / "kernel.npy").write_bytes(b"\x01" * 100)
    (d1 / "surface.meta.json").write_text(
        json.dumps({"write_id": 1, "writer": "writer-1", "bytes_len": 100, "written_at": "2026-09-12T13:00:01Z"})
    )

    # 2. Valid <stem>.meta.json pair (.png)
    d2 = root / "nested" / "p2"
    d2.mkdir(parents=True)
    (d2 / "view.png").write_bytes(b"\x02" * 200)
    (d2 / "view.meta.json").write_text(
        json.dumps({"write_id": 2, "writer": "writer-2", "bytes_len": 200, "written_at": "2026-09-12T13:00:02Z"})
    )

    # 3. Both surface.meta.json and <stem>.meta.json
    d3 = root / "p3"
    d3.mkdir()
    (d3 / "render.png").write_bytes(b"\x03" * 300)
    (d3 / "surface.meta.json").write_text(
        json.dumps({"write_id": 3, "writer": "writer-3", "bytes_len": 300, "written_at": "2026-09-12T13:00:03Z"})
    )
    (d3 / "render.meta.json").write_text(
        json.dumps({"write_id": 993, "writer": "writer-ignored", "bytes_len": 300})
    )

    # 4. Stem collision (.npy and .png sharing stem.meta.json)
    d4 = root / "p4"
    d4.mkdir()
    (d4 / "collision.npy").write_bytes(b"\x04" * 400)
    (d4 / "collision.png").write_bytes(b"\x04" * 400)
    (d4 / "collision.meta.json").write_text(
        json.dumps({"write_id": 4, "writer": "writer-4", "bytes_len": 400, "written_at": "2026-09-12T13:00:04Z"})
    )

    # 5. Skips: orphan image, bad json, missing write_id
    d_skip = root / "skips"
    d_skip.mkdir()
    (d_skip / "orphan.npy").write_bytes(b"\x00" * 10)
    (d_skip / "bad.npy").write_bytes(b"\x00" * 10)
    (d_skip / "surface.meta.json").write_text("{not json")

    reg = WriteRegistry(index_path=str(tmp_path / "reg_index.jsonl"))
    scan_records = reg.scan(str(root))

    store = ArchiveStore(str(root))
    plan_evictions = store.plan(RetentionPolicy(keep_total=0))

    scan_set = {
        (r.write_id, r.writer, r.image_path, r.sidecar_path, r.bytes_len, r.written_at)
        for r in scan_records
    }
    plan_set = {
        (
            e.record.write_id,
            e.record.writer,
            e.record.image_path,
            e.record.sidecar_path,
            e.record.bytes_len,
            e.record.written_at,
        )
        for e in plan_evictions
    }

    assert len(scan_set) == 4
    assert scan_set == plan_set
