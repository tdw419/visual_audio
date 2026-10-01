"""tests/test_spine_r1_plan.py — Gate for SPINE-R1 Phase 3 Step 1: ArchiveStore.plan().

Legs:
- L1 — N pairs -> N records: 3 dirs with kernel_memory.npy + surface.meta.json
       (write_id 1/2/3, writer 'stage-a', distinct bytes_len).
       plan(RetentionPolicy(keep_total=0)) returns 3 evictions, reason REASON_OVER_COUNT,
       ordered by (write_id, image_path).
- L2 — records are PARSED, not fabricated: tagged write ("scratch") evicted with
       reason REASON_POLICY_EXCLUDED under exclude_tags=("scratch",); bytes_len preserved.
- L3a — sidecar-less image skipped: orphan/only.npy does not break L1 evictions.
- L3b — unattributable sidecar skipped: bad/x.npy + bad/surface.meta.json with no write_id
        skipped without exception.
- L4 — read-only proof: sha256 + size snapshot of tree before and after plan() calls is identical.
- L5 — determinism: two calls on identical tree produce identical [(write_id, reason, image_path)].
- L6 — nonexistent dir: returns [] and does not create directory.
- L7 — plan_cache is populated with the returned eviction list.
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
    ArchiveStore,
    RetentionPolicy,
    REASON_OVER_COUNT,
    REASON_POLICY_EXCLUDED,
)


def _snapshot_tree(root: Path) -> dict[str, tuple[str, int]]:
    """Snapshot relative path -> (sha256, size) for all files under root."""
    snapshot: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(root))
            data = path.read_bytes()
            snapshot[rel] = (hashlib.sha256(data).hexdigest(), len(data))
    return snapshot


def _setup_three_dirs(base: Path) -> None:
    """Create 3 subdirectories with kernel_memory.npy and surface.meta.json."""
    for i, byte_len in [(1, 100), (2, 200), (3, 300)]:
        d = base / f"dir_{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "kernel_memory.npy").write_bytes(b"\x00" * byte_len)
        meta = {
            "write_id": i,
            "writer": "stage-a",
            "bytes_len": byte_len,
            "written_at": f"2026-09-12T12:00:0{i}Z",
        }
        (d / "surface.meta.json").write_text(json.dumps(meta))


def test_l1_n_pairs_n_records(tmp_path: Path) -> None:
    """L1: N pairs -> N records. plan(keep_total=0) returns 3 evictions ordered by (write_id, image_path)."""
    _setup_three_dirs(tmp_path)
    store = ArchiveStore(str(tmp_path))
    evictions = store.plan(RetentionPolicy(keep_total=0))

    assert len(evictions) == 3
    assert all(e.reason == REASON_OVER_COUNT for e in evictions)
    assert [e.record.write_id for e in evictions] == [1, 2, 3]
    assert evictions == sorted(evictions, key=lambda e: (e.record.write_id, e.record.image_path))


def test_l2_records_parsed(tmp_path: Path) -> None:
    """L2: records are PARSED, not fabricated. Exclude tags fire and bytes_len survives."""
    _setup_three_dirs(tmp_path)
    meta2 = {
        "write_id": 2,
        "writer": "stage-a",
        "bytes_len": 200,
        "written_at": "2026-09-12T12:00:02Z",
        "tags": ["scratch"],
    }
    (tmp_path / "dir_2" / "surface.meta.json").write_text(json.dumps(meta2))

    store = ArchiveStore(str(tmp_path))
    evictions = store.plan(RetentionPolicy(exclude_tags=("scratch",)))

    assert len(evictions) == 1
    assert evictions[0].record.write_id == 2
    assert evictions[0].reason == REASON_POLICY_EXCLUDED
    assert evictions[0].record.bytes_len == 200


def test_l3a_orphan_image_skipped(tmp_path: Path) -> None:
    """L3a: sidecar-less image is skipped, not fatal."""
    _setup_three_dirs(tmp_path)
    orphan = tmp_path / "orphan"
    orphan.mkdir()
    (orphan / "only.npy").write_bytes(b"orphan")

    store = ArchiveStore(str(tmp_path))
    evictions = store.plan(RetentionPolicy(keep_total=0))

    assert len(evictions) == 3
    assert [e.record.write_id for e in evictions] == [1, 2, 3]


def test_l3b_unattributable_sidecar_skipped(tmp_path: Path) -> None:
    """L3b: unattributable sidecar is skipped."""
    _setup_three_dirs(tmp_path)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "x.npy").write_bytes(b"bad_image")
    (bad / "surface.meta.json").write_text(json.dumps({"writer": "stage-a"}))

    store = ArchiveStore(str(tmp_path))
    evictions = store.plan(RetentionPolicy(keep_total=0))

    assert len(evictions) == 3
    assert [e.record.write_id for e in evictions] == [1, 2, 3]


def test_l4_read_only_proof(tmp_path: Path) -> None:
    """L4: read-only proof. Snapshot before and after plan() calls is identical."""
    _setup_three_dirs(tmp_path)
    before = _snapshot_tree(tmp_path)

    store = ArchiveStore(str(tmp_path))
    store.plan(RetentionPolicy(keep_total=0))
    store.plan(RetentionPolicy(keep_total=1))

    after = _snapshot_tree(tmp_path)
    assert before == after


def test_l5_determinism(tmp_path: Path) -> None:
    """L5: determinism. Two calls on the same tree give identical evictions."""
    _setup_three_dirs(tmp_path)
    store = ArchiveStore(str(tmp_path))
    e1 = store.plan(RetentionPolicy(keep_total=0))
    e2 = store.plan(RetentionPolicy(keep_total=0))

    list1 = [(e.record.write_id, e.reason, e.record.image_path) for e in e1]
    list2 = [(e.record.write_id, e.reason, e.record.image_path) for e in e2]
    assert list1 == list2
    assert len(list1) == 3


def test_l6_nonexistent_dir(tmp_path: Path) -> None:
    """L6: nonexistent dir returns [] and does not create the path."""
    nonexistent = tmp_path / "does_not_exist"
    assert not nonexistent.exists()

    store = ArchiveStore(str(nonexistent))
    res = store.plan(RetentionPolicy(keep_total=0))

    assert res == []
    assert not nonexistent.exists()


def test_l7_plan_cache_populated(tmp_path: Path) -> None:
    """L7: plan_cache is populated with the same list the call returned."""
    _setup_three_dirs(tmp_path)
    store = ArchiveStore(str(tmp_path))
    assert store.plan_cache == []

    evictions = store.plan(RetentionPolicy(keep_total=0))
    assert store.plan_cache == evictions
    assert len(store.plan_cache) == 3


def test_stem_sidecar_pairing(tmp_path: Path) -> None:
    """Stem pairing: image pairs with <image-stem>.meta.json when surface.meta.json is absent."""
    d = tmp_path / "stem_test"
    d.mkdir()
    (d / "render.png").write_bytes(b"fake_png")
    meta = {
        "write_id": 42,
        "writer": "renderer",
        "bytes_len": 500,
        "written_at": "2026-09-12T12:00:42Z",
    }
    (d / "render.meta.json").write_text(json.dumps(meta))

    store = ArchiveStore(str(tmp_path))
    evictions = store.plan(RetentionPolicy(keep_total=0))

    assert len(evictions) == 1
    assert evictions[0].record.write_id == 42
    assert evictions[0].record.writer == "renderer"
    assert evictions[0].record.bytes_len == 500
