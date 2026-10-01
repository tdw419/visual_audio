"""tests/test_spine_r2_wirein.py — Gate for SPINE-R2-WIREIN.

Ruling: .builder_queue/RULING_spine_wirein.md (OPTION 2).
Roadmap: systems/GLYPH_SELF_HOSTING_ROADMAP.md row SPINE-R2-WIREIN.

Six gate legs (verbatim from the ruling):
1. Best-effort append, negative control.
   Point the publish path at a read-only/unwritable registry path in a temp dir ->
   publish SUCCEEDS, and the sidecar has unattributed: true with a non-empty reason.
2. Happy path.
   A successful publish appends exactly one line, and line_sha of that line equals
   line_sha_for(entry) — no drift between mint and index.
3. --plan is non-destructive.
   Fixture where one archive is registry-referenced: --plan writes a plan, exits 0,
   and every file still exists afterwards (assert by directory listing before/after).
4. --apply is idempotent.
   First --apply removes exactly the planned set; a second --apply is a no-op
   (exit 0, nothing further removed).
5. Refusal.
   A plan that would evict a registry-referenced archive exits 2, writes the reason,
   and deletes nothing.
6. Default is inert.
   --apply with no policy flags evicts nothing and says so.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.geos_archive import (
    ArchiveRecord,
    parse_record,
)
from tools.geos_emit import ACK_SENTINEL, GeosEmitter
from tools.geos_registry import (
    RegistryEntry,
    entry_line,
    line_sha_for,
)


def _make_pair(d: Path, write_id: int, writer: str, byte_len: int) -> Tuple[Path, Path]:
    """Create <d>/kernel_memory.npy and <d>/surface.meta.json."""
    d.mkdir(parents=True, exist_ok=True)
    img_path = d / "kernel_memory.npy"
    sidecar_path = d / "surface.meta.json"
    img_path.write_bytes(b"K" * byte_len)
    meta = {
        "write_id": write_id,
        "writer": writer,
        "bytes_len": byte_len,
        "written_at": f"2026-09-13T12:00:0{write_id}Z",
    }
    sidecar_path.write_text(json.dumps(meta))
    return img_path, sidecar_path


def _record_for(img_path: Path, sidecar_path: Path) -> ArchiveRecord:
    """Build ArchiveRecord from sidecar on disk."""
    with open(sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return parse_record(meta, image_path=str(img_path), sidecar_path=str(sidecar_path))


def test_l1_best_effort_append_negative_control(tmp_path: Path) -> None:
    """Leg 1: Best-effort append, negative control.

    Point the publish path at a read-only/unwritable registry path in a temp dir ->
    publish SUCCEEDS, and the sidecar has unattributed: true with a non-empty reason.
    """
    pub = tmp_path / "pub"
    pub.mkdir(parents=True, exist_ok=True)
    mem = np.zeros(16384, dtype=np.uint32)
    np.save(pub / "kernel_memory.npy", mem)

    ack = tmp_path / ".geos_emit_ack"
    ack.write_text(ACK_SENTINEL)

    ro_dir = tmp_path / "ro_dir"
    ro_dir.mkdir(parents=True, exist_ok=True)
    ro_reg = ro_dir / "unwritable_index.jsonl"
    ro_reg.write_text("")
    ro_reg.chmod(0o444)
    ro_dir.chmod(0o555)

    try:
        em = GeosEmitter(publish_dir=pub, ack_file=ack, registry_path=ro_reg)
        res = em.emit(
            {
                "kind": "post",
                "box": 0,
                "op": 1,
                "payload": 2,
                "word": 750,
                "writer": "stage-negative-control",
            }
        )

        # Publish must SUCCEED
        assert res["committed"] is True
        assert res["write_id"] == 1
        assert res["writer"] == "stage-negative-control"

        # Sidecar must record unattributed: true and non-empty reason
        meta_file = pub / "surface.meta.json"
        assert meta_file.is_file()
        meta = json.loads(meta_file.read_text())
        assert meta.get("unattributed") is True
        reason = meta.get("unattributed_reason")
        assert isinstance(reason, str)
        assert len(reason) > 0

        # Archive sidecar must also reflect unattributed status
        archive_meta = pub / "archive" / "surface.meta.1.json"
        assert archive_meta.is_file()
        arc_meta = json.loads(archive_meta.read_text())
        assert arc_meta.get("unattributed") is True
        assert arc_meta.get("unattributed_reason") == reason

    finally:
        ro_dir.chmod(0o755)
        ro_reg.chmod(0o644)


def test_l2_happy_path(tmp_path: Path) -> None:
    """Leg 2: Happy path.

    A successful publish appends exactly one line, and line_sha of that line equals
    line_sha_for(entry) — no drift between mint and index.
    """
    pub = tmp_path / "pub_happy"
    pub.mkdir(parents=True, exist_ok=True)
    mem = np.zeros(16384, dtype=np.uint32)
    np.save(pub / "kernel_memory.npy", mem)

    ack = tmp_path / ".geos_emit_ack"
    ack.write_text(ACK_SENTINEL)

    reg_file = tmp_path / "spine_index.jsonl"
    em = GeosEmitter(
        publish_dir=pub,
        ack_file=ack,
        registry_path=reg_file,
        origin_id="origin-happy",
    )

    res = em.emit(
        {
            "kind": "post",
            "box": 0,
            "op": 1,
            "payload": 42,
            "word": 750,
            "writer": "stage-happy",
        }
    )

    assert res["committed"] is True

    # Sidecar on success must NOT carry unattributed: true
    meta_file = pub / "surface.meta.json"
    meta = json.loads(meta_file.read_text())
    assert not meta.get("unattributed")
    assert "unattributed_reason" not in meta

    # Registry must exist and have EXACTLY ONE line
    assert reg_file.is_file()
    lines = reg_file.read_text().splitlines()
    assert len(lines) == 1

    entry_data = json.loads(lines[0])
    assert entry_data["origin_id"] == "origin-happy"
    assert entry_data["write_id"] == 1
    assert entry_data["writer"] == "stage-happy"

    # Reconstruct record from sidecar and verify line_sha
    rec = parse_record(
        meta,
        image_path=entry_data["image_path"],
        sidecar_path=str(meta_file),
    )
    expected_line_sha = line_sha_for(rec)
    assert entry_data["line_sha"] == expected_line_sha


def test_l3_plan_is_non_destructive(tmp_path: Path) -> None:
    """Leg 3: --plan is non-destructive.

    Fixture where one archive is registry-referenced: --plan writes a plan,
    exits 0, and every file still exists afterwards (assert by directory listing before/after).
    """
    arch = tmp_path / "arch"
    img1, meta1 = _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    img2, meta2 = _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=100)

    # Write 2 is referenced by registry (valid, no conflict)
    reg_file = tmp_path / "spine_index.jsonl"
    rec2 = _record_for(img2, meta2)
    entry2 = RegistryEntry(
        origin_id="origin-x",
        write_id=2,
        writer=rec2.writer,
        image_path=rec2.image_path,
        line_sha=line_sha_for(rec2),
        written_at=rec2.written_at,
    )
    reg_file.write_text(entry_line(entry2) + "\n")

    # Snapshot directory contents before running --plan
    before_files = sorted(p.relative_to(arch) for p in arch.rglob("*"))
    before_bytes = {
        p: p.read_bytes() for p in arch.rglob("*") if p.is_file()
    }

    cmd = [
        sys.executable,
        "tools/geos_retain.py",
        "--archive-dir",
        str(arch),
        "--registry-path",
        str(reg_file),
        "--keep-last",
        "1",
        "--plan",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    assert proc.returncode == 0, f"stdout: {proc.stdout}, stderr: {proc.stderr}"

    # Plan file was written
    plan_file = arch / "retention_plan.json"
    assert plan_file.is_file()
    plan_data = json.loads(plan_file.read_text())
    assert plan_data["status"] == "ok"
    assert len(plan_data["evictions"]) == 1
    assert plan_data["evictions"][0]["write_id"] == 1

    # Every file that existed before still exists with identical bytes
    after_archive_bytes = {
        p: p.read_bytes()
        for p in arch.rglob("*")
        if p.is_file() and p.name != "retention_plan.json"
    }
    assert after_archive_bytes == before_bytes

    after_files = sorted(
        p.relative_to(arch)
        for p in arch.rglob("*")
        if p.name != "retention_plan.json"
    )
    assert after_files == before_files


def test_l4_apply_is_idempotent(tmp_path: Path) -> None:
    """Leg 4: --apply is idempotent.

    First --apply removes exactly the planned set; a second --apply is a no-op
    (exit 0, nothing further removed).
    """
    arch = tmp_path / "arch"
    _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=100)
    _make_pair(arch / "w3", write_id=3, writer="stage-a", byte_len=100)

    cmd = [
        sys.executable,
        "tools/geos_retain.py",
        "--archive-dir",
        str(arch),
        "--keep-last",
        "1",
        "--apply",
    ]

    # First apply
    proc1 = subprocess.run(cmd, capture_output=True, text=True)
    assert proc1.returncode == 0, f"stdout: {proc1.stdout}, stderr: {proc1.stderr}"

    # Writes 1 and 2 removed, write 3 remains
    assert not (arch / "w1" / "kernel_memory.npy").exists()
    assert not (arch / "w1" / "surface.meta.json").exists()
    assert not (arch / "w2" / "kernel_memory.npy").exists()
    assert not (arch / "w2" / "surface.meta.json").exists()
    assert (arch / "w3" / "kernel_memory.npy").exists()
    assert (arch / "w3" / "surface.meta.json").exists()

    snapshot1 = {
        p: p.read_bytes()
        for p in arch.rglob("*")
        if p.is_file() and p.name != "retention_plan.json"
    }

    # Second apply — no-op
    proc2 = subprocess.run(cmd, capture_output=True, text=True)
    assert proc2.returncode == 0, f"stdout: {proc2.stdout}, stderr: {proc2.stderr}"
    assert "0 files deleted" in proc2.stdout

    snapshot2 = {
        p: p.read_bytes()
        for p in arch.rglob("*")
        if p.is_file() and p.name != "retention_plan.json"
    }
    assert snapshot2 == snapshot1


def test_l5_refusal(tmp_path: Path) -> None:
    """Leg 5: Refusal.

    A plan that would evict a registry-referenced archive exits 2, writes the reason,
    and deletes nothing.
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

    reg_file = tmp_path / "conflict_index.jsonl"
    reg_file.write_text(entry_line(entry_a1) + "\n" + entry_line(entry_b) + "\n")

    snapshot_before = {
        p: p.read_bytes() for p in arch.rglob("*") if p.is_file()
    }

    cmd = [
        sys.executable,
        "tools/geos_retain.py",
        "--archive-dir",
        str(arch),
        "--registry-path",
        str(reg_file),
        "--keep-last",
        "1",
        "--apply",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Must exit with code 2 (refused)
    assert proc.returncode == 2, f"expected rc 2, got {proc.returncode}. stdout: {proc.stdout}, stderr: {proc.stderr}"

    # Reason must be in stderr
    assert "refusing to compact" in proc.stderr
    assert repr(("origin-x", 1)) in proc.stderr

    # Reason must be in plan file
    plan_file = arch / "retention_plan.json"
    assert plan_file.is_file()
    plan_data = json.loads(plan_file.read_text())
    assert plan_data["status"] == "refused"
    assert "refusing to compact" in plan_data["reason"]

    # Nothing must be deleted
    snapshot_after = {
        p: p.read_bytes()
        for p in arch.rglob("*")
        if p.is_file() and p.name != "retention_plan.json"
    }
    assert snapshot_after == snapshot_before
    assert a_w1_img.is_file()
    assert a_w1_meta.is_file()
    assert a_w2_img.is_file()
    assert a_w2_meta.is_file()


def test_l6_default_is_inert(tmp_path: Path) -> None:
    """Leg 6: Default is inert.

    --apply with no policy flags evicts nothing and says so.
    """
    arch = tmp_path / "arch"
    _make_pair(arch / "w1", write_id=1, writer="stage-a", byte_len=100)
    _make_pair(arch / "w2", write_id=2, writer="stage-a", byte_len=100)

    snapshot_before = {
        p: p.read_bytes() for p in arch.rglob("*") if p.is_file()
    }

    cmd = [
        sys.executable,
        "tools/geos_retain.py",
        "--archive-dir",
        str(arch),
        "--apply",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    assert proc.returncode == 0, f"expected rc 0, got {proc.returncode}. stderr: {proc.stderr}"
    assert "inert" in proc.stdout.lower() or "nothing" in proc.stdout.lower()

    # Nothing deleted
    snapshot_after = {
        p: p.read_bytes() for p in arch.rglob("*") if p.is_file()
    }
    assert snapshot_after == snapshot_before
