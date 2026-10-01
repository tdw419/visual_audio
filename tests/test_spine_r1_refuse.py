"""tests/test_spine_r1_refuse.py — Gate for SPINE-R1 Phase 3 Step 3: compact() registry cross-reference refusal.

Legs:
- L1 — positive refusal, cross-directory conflict:
       Archive A with w1 (write_id 1) and w2 (write_id 2). plan(keep_total=1) -> evicts w1.
       Second directory B with write_id 1. Registry holds 2 entries with key ("origin-x", 1),
       different line_sha. compact(plan) raises ValueError, message contains required components,
       whole tree untouched.
- L2 — discriminating negatives (must NOT refuse):
       (a) same key ("origin-x", 1), identical line_sha on both entries (duplicate registration) -> compact proceeds.
       (b) two registry entries with different keys -> compact proceeds.
       (c) single entry, key appears once -> compact proceeds.
- L3 — no registry / empty registry:
       ArchiveStore with registry=None and ArchiveStore with WriteRegistry(entries=[]) ->
       both return {"deleted": 2, "bytes": b}, matching rule-free reference run.
- L4 — refusal happens before ANY deletion:
       Plan with 2 evictions where the second is conflicting (first is clean) ->
       raises ValueError, first eviction's files still exist with unchanged sha256, full tree unchanged.
- L5 — partial-eviction requirement is real:
       Conflicted key K where both claimants are in the plan (both evicted, distinct line_sha) ->
       no refusal, compact proceeds.
- L6 — message is literal and complete:
       On L1 fixture, assert message contains "refusing to compact", repr(key), evicted image path,
       sibling image path, and is a ValueError.
- L7 — step-2 contract still holds through new path:
       3 pairs, keep_total=1 -> 2 evictions -> deleted == 4, bytes == sum of 4 sizes, bystanders intact,
       second compact(plan) -> {"deleted": 0, "bytes": 0}.
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
    REASON_OVER_COUNT,
    parse_record,
)
from tools.geos_registry import (
    RegistryEntry,
    WriteRegistry,
    line_sha_for,
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


def _make_pair(d: Path, write_id: int, writer: str, byte_len: int) -> tuple[Path, Path]:
    """Write <d>/kernel_memory.npy and <d>/surface.meta.json."""
    d.mkdir(parents=True, exist_ok=True)
    img_path = d / "kernel_memory.npy"
    sidecar_path = d / "surface.meta.json"
    img_path.write_bytes(b"K" * byte_len)
    meta = {
        "write_id": write_id,
        "writer": writer,
        "bytes_len": byte_len,
        "written_at": f"2026-09-12T12:00:0{write_id}Z",
    }
    sidecar_path.write_text(json.dumps(meta))
    return img_path, sidecar_path


def _record_for(img_path: Path, sidecar_path: Path) -> ArchiveRecord:
    """Build ArchiveRecord using parse_record."""
    with open(sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return parse_record(meta, image_path=str(img_path), sidecar_path=str(sidecar_path))


def test_l1_positive_refusal_cross_directory_conflict(tmp_path: Path) -> None:
    """L1: positive refusal, cross-directory conflict.

    Archive root A=tmp/arch with pairs A/w1/ (write_id 1) and A/w2/ (write_id 2), both writer stage-a;
    plan = store.plan(RetentionPolicy(keep_total=1)) -> 1 eviction (write_id 1).
    Second directory B=tmp/other holding a real pair (B/kernel_memory.npy + sidecar, write_id 1 of its own emitter).
    Registry: two entries with key ("origin-x", 1) — one with image_path=A/w1/kernel_memory.npy
    and line_sha from the evicted record, one with image_path=B/kernel_memory.npy and a different line_sha.
    pytest.raises(ValueError); assert message contains "refusing to compact", repr(("origin-x", 1)),
    evicted path and sibling path; assert whole tree of tmp_path is byte-identical to pre-call snapshot.
    """
    arch = tmp_path / "arch"
    other = tmp_path / "other"

    a_w1_img, a_w1_meta = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    a_w2_img, a_w2_meta = _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)
    b_img, b_meta = _make_pair(other, write_id=1, writer="stage-b", byte_len=150)

    rec_a1 = _record_for(a_w1_img, a_w1_meta)
    rec_b = _record_for(b_img, b_meta)

    entry_a1 = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_a1.writer,
        image_path=rec_a1.image_path,
        line_sha=line_sha_for(rec_a1),
        written_at=rec_a1.written_at,
    )
    entry_b = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_b.writer,
        image_path=rec_b.image_path,
        line_sha=line_sha_for(rec_b),
        written_at=rec_b.written_at,
    )

    # Assert fixture precondition: different line_sha
    rows = [entry_a1, entry_b]
    assert len({e.line_sha for e in rows}) > 1
    assert entry_a1.key == entry_b.key == ("origin-x", 1)

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"), entries=rows)
    store = ArchiveStore(archive_dir=str(arch), registry=reg)

    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 1
    assert plan[0].record.write_id == 1

    before_snapshot = _snapshot_tree(tmp_path)

    with pytest.raises(ValueError) as excinfo:
        store.compact(plan)

    msg = str(excinfo.value)
    assert "refusing to compact" in msg
    assert repr(("origin-x", 1)) in msg
    assert str(a_w1_img) in msg
    assert str(b_img) in msg

    # Whole tree of tmp_path must be byte-identical to pre-call snapshot
    after_snapshot = _snapshot_tree(tmp_path)
    assert after_snapshot == before_snapshot


def test_l2_discriminating_negatives(tmp_path: Path) -> None:
    """L2: discriminating negatives (must NOT refuse).

    (a) same key ("origin-x", 1), identical line_sha on both entries (duplicate registration) ->
        compact(plan) proceeds and returns {"deleted": 2, "bytes": <pre-delete sizes of the 2 evicted files>};
    (b) two registry entries with different keys -> proceeds, same result;
    (c) single entry, key appears once -> proceeds.
    Each sub-leg uses a fresh copy of the fixture tree.
    """
    # Helper to setup an independent fixture tree
    def setup_subleg(sub_name: str) -> tuple[Path, ArchiveStore, list[Eviction], int]:
        sub_root = tmp_path / sub_name
        arch = sub_root / "arch"
        a_w1_img, a_w1_meta = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
        a_w2_img, a_w2_meta = _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)
        expected_bytes = os.path.getsize(a_w1_img) + os.path.getsize(a_w1_meta)
        store = ArchiveStore(archive_dir=str(arch))
        plan = store.plan(RetentionPolicy(keep_total=1))
        assert len(plan) == 1
        return sub_root, store, plan, expected_bytes

    # (a) same key ("origin-x", 1), identical line_sha on both entries
    sub_a, store_a, plan_a, expected_bytes_a = setup_subleg("sub_a")
    rec_a1 = plan_a[0].record
    entry_dup1 = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_a1.writer,
        image_path=rec_a1.image_path,
        line_sha=line_sha_for(rec_a1),
        written_at=rec_a1.written_at,
    )
    # Sibling path but identical line_sha (duplicate registration)
    entry_dup2 = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_a1.writer,
        image_path=str(sub_a / "other" / "kernel_memory.npy"),
        line_sha=line_sha_for(rec_a1),
        written_at=rec_a1.written_at,
    )
    assert len({entry_dup1.line_sha, entry_dup2.line_sha}) == 1
    assert entry_dup1.key == entry_dup2.key == ("origin-x", 1)

    store_a.registry = WriteRegistry(index_path=str(sub_a / "index.jsonl"), entries=[entry_dup1, entry_dup2])
    res_a = store_a.compact(plan_a)
    assert res_a == {"deleted": 2, "bytes": expected_bytes_a}

    # (b) two registry entries with different keys
    sub_b, store_b, plan_b, expected_bytes_b = setup_subleg("sub_b")
    rec_b1 = plan_b[0].record
    other_img, other_meta = _make_pair(sub_b / "other", write_id=99, writer="stage-b", byte_len=120)
    rec_other = _record_for(other_img, other_meta)
    entry_b1 = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_b1.writer,
        image_path=rec_b1.image_path,
        line_sha=line_sha_for(rec_b1),
        written_at=rec_b1.written_at,
    )
    entry_b2 = RegistryEntry(
        origin_id="origin-x",
        write_id=99,
        writer=rec_other.writer,
        image_path=rec_other.image_path,
        line_sha=line_sha_for(rec_other),
        written_at=rec_other.written_at,
    )
    assert entry_b1.key != entry_b2.key
    store_b.registry = WriteRegistry(index_path=str(sub_b / "index.jsonl"), entries=[entry_b1, entry_b2])
    res_b = store_b.compact(plan_b)
    assert res_b == {"deleted": 2, "bytes": expected_bytes_b}

    # (c) single entry, key appears once
    sub_c, store_c, plan_c, expected_bytes_c = setup_subleg("sub_c")
    rec_c1 = plan_c[0].record
    entry_c1 = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_c1.writer,
        image_path=rec_c1.image_path,
        line_sha=line_sha_for(rec_c1),
        written_at=rec_c1.written_at,
    )
    store_c.registry = WriteRegistry(index_path=str(sub_c / "index.jsonl"), entries=[entry_c1])
    res_c = store_c.compact(plan_c)
    assert res_c == {"deleted": 2, "bytes": expected_bytes_c}


def test_l3_no_registry_and_empty_registry(tmp_path: Path) -> None:
    """L3: no registry / empty registry.

    ArchiveStore(archive_dir=A, registry=None) and
    ArchiveStore(archive_dir=A, registry=WriteRegistry(index_path=...)) (entries empty) ->
    both return the step-2 numbers {"deleted": 2, "bytes": b}; result must be identical
    for the two stores (assert equality of the dicts and equality against a rule-free
    reference run on a third identical tree).
    """
    def make_tree(name: str) -> tuple[Path, int]:
        arch = tmp_path / name / "arch"
        w1_img, w1_meta = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
        _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)
        expected_bytes = os.path.getsize(w1_img) + os.path.getsize(w1_meta)
        return arch, expected_bytes

    # Tree 1: registry is None
    arch1, b1 = make_tree("tree1")
    store1 = ArchiveStore(archive_dir=str(arch1), registry=None)
    plan1 = store1.plan(RetentionPolicy(keep_total=1))
    res1 = store1.compact(plan1)

    # Tree 2: registry is empty WriteRegistry
    arch2, b2 = make_tree("tree2")
    reg2 = WriteRegistry(index_path=str(tmp_path / "tree2" / "index.jsonl"), entries=[])
    store2 = ArchiveStore(archive_dir=str(arch2), registry=reg2)
    plan2 = store2.plan(RetentionPolicy(keep_total=1))
    res2 = store2.compact(plan2)

    # Tree 3: rule-free reference store
    arch3, b3 = make_tree("tree3")
    store3 = ArchiveStore(archive_dir=str(arch3))
    plan3 = store3.plan(RetentionPolicy(keep_total=1))
    res3 = store3.compact(plan3)

    assert b1 == b2 == b3
    assert res1 == {"deleted": 2, "bytes": b1}
    assert res1 == res2 == res3


def test_l4_refusal_happens_before_any_deletion(tmp_path: Path) -> None:
    """L4: refusal happens before ANY deletion.

    Plan with two evictions where the second is the conflicting one (the first is fully clean):
    pytest.raises(ValueError) and the first eviction's two files still exist with unchanged sha256;
    full-tree snapshot equals the pre-call snapshot. This proves the pre-pass is complete before
    the delete loop, not an incremental check.
    """
    arch = tmp_path / "arch"
    other = tmp_path / "other"

    w1_img, w1_meta = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    w2_img, w2_meta = _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)
    w3_img, w3_meta = _make_pair(arch / "w3", write_id=3, writer="stage-a", byte_len=300)
    other_img, other_meta = _make_pair(other, write_id=2, writer="stage-b", byte_len=250)

    rec_w1 = _record_for(w1_img, w1_meta)
    rec_w2 = _record_for(w2_img, w2_meta)
    rec_other = _record_for(other_img, other_meta)

    # Registry has conflicting entries for write_id 2 only.
    # write_id 1 has NO entries in registry (fully clean).
    entry_w2 = RegistryEntry(
        origin_id="origin-x",
        write_id=2,
        writer=rec_w2.writer,
        image_path=rec_w2.image_path,
        line_sha=line_sha_for(rec_w2),
        written_at=rec_w2.written_at,
    )
    entry_other = RegistryEntry(
        origin_id="origin-x",
        write_id=2,
        writer=rec_other.writer,
        image_path=rec_other.image_path,
        line_sha=line_sha_for(rec_other),
        written_at=rec_other.written_at,
    )

    rows = [entry_w2, entry_other]
    assert len({e.line_sha for e in rows}) > 1

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"), entries=rows)
    store = ArchiveStore(archive_dir=str(arch), registry=reg)

    # keep_total=1 -> evicts write_id 1 and write_id 2 (in order: w1 then w2)
    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 2
    assert [e.record.write_id for e in plan] == [1, 2]

    before_tree = _snapshot_tree(tmp_path)
    w1_img_sha = hashlib.sha256(w1_img.read_bytes()).hexdigest()
    w1_meta_sha = hashlib.sha256(w1_meta.read_bytes()).hexdigest()

    with pytest.raises(ValueError) as excinfo:
        store.compact(plan)

    assert "refusing to compact" in str(excinfo.value)
    assert repr(("origin-x", 2)) in str(excinfo.value)

    # First eviction's files still exist with unchanged sha256
    assert w1_img.exists()
    assert w1_meta.exists()
    assert hashlib.sha256(w1_img.read_bytes()).hexdigest() == w1_img_sha
    assert hashlib.sha256(w1_meta.read_bytes()).hexdigest() == w1_meta_sha

    # Full-tree snapshot equals pre-call snapshot
    assert _snapshot_tree(tmp_path) == before_tree


def test_l5_partial_eviction_requirement_is_real(tmp_path: Path) -> None:
    """L5: partial-eviction requirement is real.

    Conflicted key K where both claimants are in the plan (both evicted, distinct line_sha) ->
    no refusal, compact proceeds (the conflict's files are all being removed together; nothing
    survives to be inconsistent). Assert the returned counts.
    """
    arch = tmp_path / "arch"

    # Both claimants live inside the archive and are both evicted by the plan
    w1a_img, w1a_meta = _make_pair(arch / "w1a", write_id=1, writer="stage-a", byte_len=100)
    w1b_img, w1b_meta = _make_pair(arch / "w1b", write_id=1, writer="stage-b", byte_len=150)
    w2_img, w2_meta = _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)

    rec_1a = _record_for(w1a_img, w1a_meta)
    rec_1b = _record_for(w1b_img, w1b_meta)

    entry_1a = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_1a.writer,
        image_path=rec_1a.image_path,
        line_sha=line_sha_for(rec_1a),
        written_at=rec_1a.written_at,
    )
    entry_1b = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_1b.writer,
        image_path=rec_1b.image_path,
        line_sha=line_sha_for(rec_1b),
        written_at=rec_1b.written_at,
    )

    rows = [entry_1a, entry_1b]
    assert len({e.line_sha for e in rows}) > 1
    assert entry_1a.key == entry_1b.key == ("origin-x", 1)

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"), entries=rows)
    store = ArchiveStore(archive_dir=str(arch), registry=reg)

    # keep_total=1 -> newest (write_id 2) survives, both write_id 1 records are evicted
    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 2
    evicted_image_paths = {e.record.image_path for e in plan}
    assert rec_1a.image_path in evicted_image_paths
    assert rec_1b.image_path in evicted_image_paths

    expected_bytes = (
        os.path.getsize(w1a_img)
        + os.path.getsize(w1a_meta)
        + os.path.getsize(w1b_img)
        + os.path.getsize(w1b_meta)
    )

    # compact must proceed without refusal since all claimants are evicted
    res = store.compact(plan)
    assert res == {"deleted": 4, "bytes": expected_bytes}
    assert not w1a_img.exists()
    assert not w1a_meta.exists()
    assert not w1b_img.exists()
    assert not w1b_meta.exists()
    assert w2_img.exists()
    assert w2_meta.exists()


def test_l6_message_is_literal_and_complete(tmp_path: Path) -> None:
    """L6: message is literal and complete.

    On the L1 fixture, assert the caught exception's str() contains all four required pieces:
    (substring 'refusing to compact', repr(key), evicted image path, sibling image path)
    and that it is a ValueError — not a bare Exception, not an OSError.
    """
    arch = tmp_path / "arch"
    other = tmp_path / "other"

    a_w1_img, a_w1_meta = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)
    b_img, b_meta = _make_pair(other, write_id=1, writer="stage-b", byte_len=150)

    rec_a1 = _record_for(a_w1_img, a_w1_meta)
    rec_b = _record_for(b_img, b_meta)

    entry_a1 = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_a1.writer,
        image_path=rec_a1.image_path,
        line_sha=line_sha_for(rec_a1),
        written_at=rec_a1.written_at,
    )
    entry_b = RegistryEntry(
        origin_id="origin-x",
        write_id=1,
        writer=rec_b.writer,
        image_path=rec_b.image_path,
        line_sha=line_sha_for(rec_b),
        written_at=rec_b.written_at,
    )

    rows = [entry_a1, entry_b]
    assert len({e.line_sha for e in rows}) > 1

    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"), entries=rows)
    store = ArchiveStore(archive_dir=str(arch), registry=reg)
    plan = store.plan(RetentionPolicy(keep_total=1))

    with pytest.raises(Exception) as excinfo:
        store.compact(plan)

    # Must be exact ValueError, not bare Exception or OSError
    assert type(excinfo.value) is ValueError

    msg = str(excinfo.value)
    # Piece 1: literal substring 'refusing to compact'
    assert "refusing to compact" in msg
    # Piece 2: repr(key)
    assert repr(("origin-x", 1)) in msg
    # Piece 3: evicted image path
    assert str(a_w1_img) in msg
    # Piece 4: sibling image path
    assert str(b_img) in msg


def test_l7_step2_contract_still_holds_with_registry(tmp_path: Path) -> None:
    """L7: the step-2 contract still holds through the new path.

    Re-run the step-2 essentials with a registry attached and no conflict:
    3 pairs, keep_total=1 -> 2 evictions -> deleted == 4 (file unit, not record unit),
    bytes == sum(os.path.getsize(p) for p in the 4 paths) measured pre-delete,
    bystanders intact, second compact(plan) -> {"deleted": 0, "bytes": 0} (idempotence preserved).
    """
    arch = tmp_path / "arch"
    w1_img, w1_meta = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    w2_img, w2_meta = _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=200)
    w3_img, w3_meta = _make_pair(arch / "w3", write_id=3, writer="stage-a", byte_len=300)

    # Bystander
    bystander = arch / "notes.txt"
    bystander.write_text("keep me")

    # Non-conflicting registry entry (only 1 entry for key)
    rec_w3 = _record_for(w3_img, w3_meta)
    entry_w3 = RegistryEntry(
        origin_id="origin-x",
        write_id=3,
        writer=rec_w3.writer,
        image_path=rec_w3.image_path,
        line_sha=line_sha_for(rec_w3),
        written_at=rec_w3.written_at,
    )
    reg = WriteRegistry(index_path=str(tmp_path / "index.jsonl"), entries=[entry_w3])

    store = ArchiveStore(archive_dir=str(arch), registry=reg)
    plan = store.plan(RetentionPolicy(keep_total=1))
    assert len(plan) == 2

    evicted_paths = [w1_img, w1_meta, w2_img, w2_meta]
    expected_bytes = sum(os.path.getsize(p) for p in evicted_paths)

    res1 = store.compact(plan)
    assert res1["deleted"] == 4
    assert res1["bytes"] == expected_bytes
    for p in evicted_paths:
        assert not p.exists()
    assert w3_img.exists()
    assert w3_meta.exists()
    assert bystander.exists()

    # Second compact(plan) -> {"deleted": 0, "bytes": 0} (idempotence)
    res2 = store.compact(plan)
    assert res2 == {"deleted": 0, "bytes": 0}
