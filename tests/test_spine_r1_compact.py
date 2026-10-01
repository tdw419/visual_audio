"""tests/test_spine_r1_compact.py — Gate for SPINE-R1 Phase 3 Step 2: ArchiveStore.compact().

Legs:
- L1 — exact deletion + exact accounting: 3 dirs with kernel_memory.npy + surface.meta.json
       (write_id 1/2/3, writer 'stage-a', distinct bytes_len).
       plan(keep_total=1) -> 2 evictions (4 files).
       compact(plan) -> deleted == 4 (file-count unit explicitly locked),
       bytes == pre-measured size sum.
       Kept pair (write_id 3) survives with unchanged sha256.
- L2 — nothing else is touched: bystanders present (extra write_id 99 non-planned pair, notes.txt,
       orphan/only.npy, bad/x.npy + bad/surface.meta.json with no write_id).
       Full-tree snapshot after compact equals before-snapshot minus exactly the 4 deleted paths.
       Set difference equality asserted both ways (no extra deletions, nothing missed).
- L3 — idempotence: calling compact(plan) a second time with the same plan returns {"deleted": 0, "bytes": 0},
       raises nothing, tree snapshot unchanged between the two calls.
- L4 — containment refusal: plan containing record with image_path or sidecar_path outside
       archive_dir raises ValueError naming the offending path and archive_dir; tree is untouched;
       refusal happens before any deletion.
- L5 — plan -> compact -> re-plan: after compacting an eviction plan, a fresh plan returns [].
- L6 — empty plan / nonexistent dir: compact([]) returns {"deleted": 0, "bytes": 0}; nonexistent
       archive_dir is not created and returns zeros without error.
- L7 — deleted counts files, not records (unit lock): when one sidecar is missing before compact,
       deleted == 3 for 2 evictions, bytes equals the 3 remaining files' pre-delete sizes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.geos_archive import (
    ArchiveRecord,
    ArchiveStore,
    Eviction,
    RetentionPolicy,
    REASON_OVER_BYTES,
    REASON_OVER_COUNT,
    REASON_POLICY_EXCLUDED,
    REASON_SUPERSEDED,
)


def _snapshot_tree(root: Path) -> dict[str, tuple[str, int]]:
    """Snapshot relative path -> (sha256, size) for all files under root."""
    snapshot: dict[str, tuple[str, int]] = {}
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(root))
            data = path.read_bytes()
            snapshot[rel] = (hashlib.sha256(data).hexdigest(), len(data))
    return snapshot


def _setup_archive(base: Path) -> tuple[Path, list[int]]:
    """Create 3 subdirectories under base/archive with kernel_memory.npy and surface.meta.json."""
    archive = base / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    for i, byte_len in [(1, 100), (2, 200), (3, 300)]:
        d = archive / f"w{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "kernel_memory.npy").write_bytes(b"K" * byte_len)
        meta = {
            "write_id": i,
            "writer": "stage-a",
            "bytes_len": byte_len,
            "written_at": f"2026-09-12T12:00:0{i}Z",
        }
        (d / "surface.meta.json").write_text(json.dumps(meta))
    return archive, [100, 200, 300]


def test_l1_exact_deletion_and_accounting(tmp_path: Path) -> None:
    """L1: exact deletion + exact accounting.

    3 dirs (w1/, w2/, w3/), each with kernel_memory.npy + surface.meta.json,
    write_id 1/2/3, writer 'stage-a', distinct bytes_len.
    plan(keep_total=1) -> 2 evictions.
    res["deleted"] == 4 (2 records * image+sidecar, file-count unit explicitly locked).
    res["bytes"] == sum(os.path.getsize(p) for p in the 4 paths) measured pre-delete.
    The kept pair (write_id 3) still exists with unchanged sha256; its files not counted in bytes.
    """
    archive, _ = _setup_archive(tmp_path)
    store = ArchiveStore(str(archive))
    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 2

    # Measure pre-delete sizes and collect the 4 target paths
    evicted_paths = []
    for ev in plan:
        evicted_paths.append(ev.record.image_path)
        evicted_paths.append(ev.record.sidecar_path)
    assert len(evicted_paths) == 4
    expected_bytes = sum(os.path.getsize(p) for p in evicted_paths)
    assert expected_bytes > 0

    w3_img = archive / "w3" / "kernel_memory.npy"
    w3_meta = archive / "w3" / "surface.meta.json"
    w3_img_sha_before = hashlib.sha256(w3_img.read_bytes()).hexdigest()
    w3_meta_sha_before = hashlib.sha256(w3_meta.read_bytes()).hexdigest()

    before_snapshot = _snapshot_tree(archive)

    res = store.compact(plan)

    # Assert exact deleted count and explicitly lock file-count unit (not record count)
    assert res["deleted"] == 4
    assert res["deleted"] == len(plan) * 2
    assert res["bytes"] == expected_bytes

    # Evicted files must no longer exist
    for p in evicted_paths:
        assert not os.path.exists(p)

    # Kept pair (write_id 3) still exists with unchanged sha256
    assert w3_img.exists()
    assert w3_meta.exists()
    assert hashlib.sha256(w3_img.read_bytes()).hexdigest() == w3_img_sha_before
    assert hashlib.sha256(w3_meta.read_bytes()).hexdigest() == w3_meta_sha_before

    # Kept pair sizes must not be counted in bytes
    assert res["bytes"] < sum(size for _, size in before_snapshot.values())

    # plan_cache is left untouched by compact
    assert store.plan_cache == plan


def test_l2_nothing_else_touched(tmp_path: Path) -> None:
    """L2: nothing else is touched.

    Add a non-planned pair (extra/surface.meta.json + extra/kernel_memory.npy, write_id 99),
    plus unrelated bystanders that are not archive records:
    - notes.txt
    - orphan/only.npy (no sidecar)
    - bad/x.npy + bad/surface.meta.json with no write_id
    Full-tree snapshot after compact must equal before-snapshot minus exactly the 4 deleted paths.
    Assert set difference equality both ways (no extra deletions, nothing missed).
    """
    archive, _ = _setup_archive(tmp_path)
    store = ArchiveStore(str(archive))
    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 2

    # Collect the 4 deleted paths
    deleted_rel_paths = set()
    for ev in plan:
        deleted_rel_paths.add(str(Path(ev.record.image_path).relative_to(archive)))
        deleted_rel_paths.add(str(Path(ev.record.sidecar_path).relative_to(archive)))
    assert len(deleted_rel_paths) == 4

    # Add non-planned pair (extra)
    extra_dir = archive / "extra"
    extra_dir.mkdir(parents=True, exist_ok=True)
    (extra_dir / "kernel_memory.npy").write_bytes(b"extra_npy_payload")
    (extra_dir / "surface.meta.json").write_text(
        json.dumps({"write_id": 99, "writer": "stage-a", "bytes_len": 400})
    )

    # Add bystanders
    (archive / "notes.txt").write_text("operator notes - do not delete")
    orphan_dir = archive / "orphan"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "only.npy").write_bytes(b"orphan data")

    bad_dir = archive / "bad"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "x.npy").write_bytes(b"unattributed image")
    (bad_dir / "surface.meta.json").write_text(json.dumps({"writer": "stage-a"}))

    before = _snapshot_tree(archive)

    # Verify all expected bystander files are in the before snapshot
    assert "extra/kernel_memory.npy" in before
    assert "extra/surface.meta.json" in before
    assert "notes.txt" in before
    assert "orphan/only.npy" in before
    assert "bad/x.npy" in before
    assert "bad/surface.meta.json" in before
    for rel in deleted_rel_paths:
        assert rel in before

    res = store.compact(plan)
    assert res["deleted"] == 4

    after = _snapshot_tree(archive)

    # Assert set difference equality both ways (no extra deletions, nothing missed)
    assert set(before.keys()) - set(after.keys()) == deleted_rel_paths
    assert set(after.keys()) - set(before.keys()) == set()

    # Assert all surviving files have identical sha256 and size
    for path_key in after:
        assert after[path_key] == before[path_key]


def test_l3_idempotence(tmp_path: Path) -> None:
    """L3: idempotence.

    Call compact(plan) a second time with the same plan -> returns {"deleted": 0, "bytes": 0},
    raises nothing, tree snapshot unchanged between the two calls.
    """
    archive, _ = _setup_archive(tmp_path)
    store = ArchiveStore(str(archive))
    plan = store.plan(RetentionPolicy(keep_total=1))

    res1 = store.compact(plan)
    assert res1["deleted"] == 4
    assert res1["bytes"] > 0

    snapshot_after_first = _snapshot_tree(archive)

    res2 = store.compact(plan)
    assert res2 == {"deleted": 0, "bytes": 0}

    snapshot_after_second = _snapshot_tree(archive)
    assert snapshot_after_first == snapshot_after_second


def test_l4_containment_refusal(tmp_path: Path) -> None:
    """L4: containment refusal.

    Build a plan by hand containing one record whose image_path is outside archive_dir
    and one whose sidecar escapes.
    pytest.raises(ValueError); assert message contains offending path and archive_dir.
    Assert the whole tree (including outside file) is byte-identical to pre-call snapshot
    (in-tree victim was NOT deleted either).
    Assert refusal happens before any deletion:
    first out-of-tree, second valid in-tree -> zero deletions;
    first valid in-tree, second out-of-tree -> zero deletions.
    """
    archive, _ = _setup_archive(tmp_path)
    store = ArchiveStore(str(archive))

    # Outside files
    outside_file = tmp_path / "outside.npy"
    outside_file.write_bytes(b"outside_content")
    outside_meta = tmp_path / "outside.meta.json"
    outside_meta.write_bytes(b"outside_meta_content")

    # In-tree valid files
    valid_record = ArchiveRecord(
        write_id=1,
        writer="stage-a",
        image_path=str(archive / "w1" / "kernel_memory.npy"),
        sidecar_path=str(archive / "w1" / "surface.meta.json"),
        bytes_len=100,
    )
    # Record with outside image
    bad_img_record = ArchiveRecord(
        write_id=99,
        writer="evil",
        image_path=str(outside_file),
        sidecar_path=str(archive / "w2" / "surface.meta.json"),
        bytes_len=100,
    )
    # Record with outside sidecar
    bad_meta_record = ArchiveRecord(
        write_id=98,
        writer="evil",
        image_path=str(archive / "w2" / "kernel_memory.npy"),
        sidecar_path=str(outside_meta),
        bytes_len=100,
    )

    before_tree = _snapshot_tree(tmp_path)

    # Case 4a: Out-of-tree image path, out-of-tree first, valid second
    plan_bad_img = [
        Eviction(bad_img_record, REASON_OVER_COUNT),
        Eviction(valid_record, REASON_OVER_COUNT),
    ]
    with pytest.raises(ValueError) as excinfo_img:
        store.compact(plan_bad_img)
    assert str(outside_file) in str(excinfo_img.value)
    assert str(archive) in str(excinfo_img.value)
    assert _snapshot_tree(tmp_path) == before_tree

    # Case 4b: Out-of-tree sidecar path, valid first, out-of-tree second
    # Proves validation is a full pass before any deletion (valid_record not deleted!)
    plan_bad_meta = [
        Eviction(valid_record, REASON_OVER_COUNT),
        Eviction(bad_meta_record, REASON_OVER_COUNT),
    ]
    with pytest.raises(ValueError) as excinfo_meta:
        store.compact(plan_bad_meta)
    assert str(outside_meta) in str(excinfo_meta.value)
    assert str(archive) in str(excinfo_meta.value)
    assert _snapshot_tree(tmp_path) == before_tree


def test_l5_plan_compact_replan(tmp_path: Path) -> None:
    """L5: plan -> compact -> re-plan.

    3 pairs, keep_total=1; after compact(plan), a fresh
    store.plan(RetentionPolicy(keep_total=1)) returns []
    (the evicted pairs are gone, so no eviction remains).
    """
    archive, _ = _setup_archive(tmp_path)
    store = ArchiveStore(str(archive))
    policy = RetentionPolicy(keep_total=1)

    plan1 = store.plan(policy)
    assert len(plan1) == 2

    res = store.compact(plan1)
    assert res["deleted"] == 4

    plan2 = store.plan(policy)
    assert plan2 == []


def test_l6_empty_plan_nonexistent_dir(tmp_path: Path) -> None:
    """L6: empty plan / nonexistent dir.

    compact([]) == {"deleted": 0, "bytes": 0} and no error;
    an ArchiveStore pointed at a path that does not exist gives
    plan(...) == [] then compact([]) -> zeros, and the path still does not
    exist afterwards.
    """
    # 6a: Existing archive, empty plan
    archive, _ = _setup_archive(tmp_path)
    store_exist = ArchiveStore(str(archive))
    before_tree = _snapshot_tree(archive)
    assert store_exist.compact([]) == {"deleted": 0, "bytes": 0}
    assert _snapshot_tree(archive) == before_tree

    # 6b: Nonexistent dir
    nonexistent = tmp_path / "does_not_exist"
    assert not nonexistent.exists()

    store_nonexist = ArchiveStore(str(nonexistent))
    plan = store_nonexist.plan(RetentionPolicy(keep_total=1))
    assert plan == []

    res = store_nonexist.compact([])
    assert res == {"deleted": 0, "bytes": 0}
    assert not nonexistent.exists()


def test_l7_deleted_counts_files_not_records(tmp_path: Path) -> None:
    """L7: deleted counts files, not records (unit lock).

    Fixture where the sidecar is already missing for one evicted record
    (delete the sidecar by hand before compact): deleted == 3 for 2 evictions,
    and bytes equals the 3 remaining files' pre-delete sizes.
    This leg exists so a future refactor cannot silently flip the unit.
    """
    archive, _ = _setup_archive(tmp_path)
    store = ArchiveStore(str(archive))
    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 2

    # Hand-delete the sidecar of the first eviction (w1/surface.meta.json)
    missing_sidecar = Path(plan[0].record.sidecar_path)
    assert missing_sidecar.exists()
    missing_sidecar.unlink()

    # The remaining 3 files are: plan[0].image_path, plan[1].image_path, plan[1].sidecar_path
    remaining_paths = [
        plan[0].record.image_path,
        plan[1].record.image_path,
        plan[1].record.sidecar_path,
    ]
    for p in remaining_paths:
        assert os.path.exists(p)
    expected_bytes = sum(os.path.getsize(p) for p in remaining_paths)
    assert expected_bytes > 0

    res = store.compact(plan)

    # deleted == 3 for 2 evictions (explicit unit lock!)
    assert res["deleted"] == 3
    assert res["deleted"] != len(plan)
    assert res["bytes"] == expected_bytes
