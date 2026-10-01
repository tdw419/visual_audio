"""tests/test_spine_r1_register.py — Gate for SPINE-R1 Phase 3 Step 4: WriteRegistry.register() + persistence.

Legs (8):
- L1 append basics — fresh path: register() returns entry whose key, writer, image_path,
  written_at match record and line_sha == line_sha_for(record); file exists with exactly
  one newline-terminated line == entry_line(returned_entry); json.loads(line)["write_id"]
  is record.write_id.
- L2 append-only growth — second register with new key appends exactly one more line;
  first line's bytes unchanged (prefix preserved); parsed key order == registration order.
- L3 digest/persistence — fresh path: index_digest([]) for empty log; after registers
  reg.digest() == index_digest(file_lines) == index_digest(reg.lines()); second instance
  reading file independently reproduces same key sequence.
- L4 duplicate refusal (in-memory) — same instance, same key twice -> ValueError containing
  'duplicate registry key' and repr(key); line count still 1, file md5 identical before/after.
- L5 duplicate refusal (across re-open) — new instance on same non-empty path registers key
  already on disk -> ValueError naming on-disk 1-based line number (n >= 1); file md5
  unchanged, pre-existing line byte-identical.
- L6 re-open append + prefix preservation — new instance appends genuinely new key to non-empty
  log: file grows by exactly len(entry_line(new_entry)) + 1; file_bytes[:len(before)] == before;
  parsed key set == old keys | new key; digest of preserved prefix identical before/after.
- L7 failure path is live — index_path whose parent is a regular file -> pytest.raises(OSError);
  reg.entries == []; no file appears at target path; subsequent register on valid path succeeds.
- L8 no-write refusal + bad key — empty/whitespace origin_id -> ValueError and no index file is
  created; empty (0-byte) or trailing-blank-line index treated as 'no entries' (no phantom
  duplicate, no crash).
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

from tools.geos_archive import ArchiveRecord
from tools.geos_registry import (
    RegistryEntry,
    WriteRegistry,
    entry_line,
    index_digest,
    line_sha_for,
    registry_key,
)


def test_l1_append_basics(tmp_path: Path) -> None:
    """L1 append basics: register() returns valid entry and appends single canonical line."""
    index_file = tmp_path / "sub" / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec = ArchiveRecord(
        write_id=1,
        writer="stage-a",
        image_path="out/kernel_1.npy",
        sidecar_path="out/surface_1.json",
        written_at="2026-09-12T12:00:00Z",
    )
    entry = reg.register(rec, origin_id="origin-alpha")

    # Match properties
    assert entry.key == ("origin-alpha", 1)
    assert entry.origin_id == "origin-alpha"
    assert entry.write_id == 1
    assert entry.writer == rec.writer
    assert entry.image_path == rec.image_path
    assert entry.written_at == rec.written_at
    assert entry.line_sha == line_sha_for(rec)

    # Returned entry is the exact object in self.entries
    assert len(reg.entries) == 1
    assert entry is reg.entries[0]

    # File on disk exists and has exactly one newline-terminated line
    assert index_file.is_file()
    raw_bytes = index_file.read_bytes()
    assert raw_bytes.endswith(b"\n")
    lines = raw_bytes.decode("utf-8").splitlines()
    assert len(lines) == 1

    expected_line = entry_line(entry)
    assert lines[0] == expected_line
    parsed = json.loads(lines[0])
    assert parsed["write_id"] == rec.write_id
    assert parsed["origin_id"] == "origin-alpha"
    assert parsed["writer"] == "stage-a"
    assert parsed["line_sha"] == entry.line_sha


def test_l2_append_only_growth(tmp_path: Path) -> None:
    """L2 append-only growth: appending a second key preserves the first line byte-for-byte."""
    index_file = tmp_path / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec1 = ArchiveRecord(10, "stage-a", "img_10.npy", "side_10.json", written_at="2026-09-12T10:00:00Z")
    rec2 = ArchiveRecord(20, "stage-b", "img_20.npy", "side_20.json", written_at="2026-09-12T10:05:00Z")

    entry1 = reg.register(rec1, origin_id="orig-1")
    before_bytes = index_file.read_bytes()

    entry2 = reg.register(rec2, origin_id="orig-1")
    after_bytes = index_file.read_bytes()

    # Exactly one more line
    after_lines = after_bytes.decode("utf-8").splitlines()
    assert len(after_lines) == 2

    # Prefix is untouched byte-for-byte
    assert after_bytes[: len(before_bytes)] == before_bytes
    expected_growth = (entry_line(entry2) + "\n").encode("utf-8")
    assert after_bytes[len(before_bytes) :] == expected_growth

    # Parsed key order matches registration order
    parsed_keys = [
        (json.loads(line)["origin_id"], json.loads(line)["write_id"])
        for line in after_lines
    ]
    assert parsed_keys == [entry1.key, entry2.key]


def test_l3_digest_persistence(tmp_path: Path) -> None:
    """L3 digest/persistence: digest equals index_digest(file_lines); second instance reproduces keys."""
    fresh_file = tmp_path / "empty.jsonl"
    reg_fresh = WriteRegistry(index_path=str(fresh_file))
    assert reg_fresh.digest() == index_digest([])

    index_file = tmp_path / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec1 = ArchiveRecord(1, "writer-x", "img_x.npy", "side_x.json")
    rec2 = ArchiveRecord(2, "writer-y", "img_y.npy", "side_y.json")
    reg.register(rec1, origin_id="root-a")
    reg.register(rec2, origin_id="root-b")

    file_lines = index_file.read_text(encoding="utf-8").splitlines()
    assert reg.digest() == index_digest(file_lines)
    assert reg.digest() == index_digest(reg.lines())

    # Second instance reading file independently reproduces same key sequence
    reg2 = WriteRegistry(index_path=str(index_file))
    reg2_file_lines = Path(reg2.index_path).read_text(encoding="utf-8").splitlines()
    reg2_keys = [
        (json.loads(line)["origin_id"], json.loads(line)["write_id"])
        for line in reg2_file_lines
    ]
    assert reg2_keys == [("root-a", 1), ("root-b", 2)]
    assert index_digest(reg2_file_lines) == reg.digest()


def test_l4_duplicate_refusal_in_memory(tmp_path: Path) -> None:
    """L4 duplicate refusal (in-memory): same instance, same key twice raises ValueError, file unmodified."""
    index_file = tmp_path / "spine_index.jsonl"
    reg = WriteRegistry(index_path=str(index_file))

    rec = ArchiveRecord(100, "writer-dup", "img_100.npy", "side_100.json")
    reg.register(rec, origin_id="dup-origin")

    before_bytes = index_file.read_bytes()
    before_md5 = hashlib.md5(before_bytes).hexdigest()
    assert len(reg.entries) == 1

    with pytest.raises(ValueError) as excinfo:
        reg.register(rec, origin_id="dup-origin")

    err_msg = str(excinfo.value)
    assert "duplicate registry key" in err_msg
    assert repr(("dup-origin", 100)) in err_msg
    assert "append-only index: history is never rewritten" in err_msg

    after_bytes = index_file.read_bytes()
    assert hashlib.md5(after_bytes).hexdigest() == before_md5
    assert len(after_bytes.decode("utf-8").splitlines()) == 1
    assert len(reg.entries) == 1


def test_l5_duplicate_refusal_across_reopen(tmp_path: Path) -> None:
    """L5 duplicate refusal (across re-open): new instance registers key on disk, names 1-based line number."""
    index_file = tmp_path / "spine_index.jsonl"
    reg1 = WriteRegistry(index_path=str(index_file))

    rec1 = ArchiveRecord(101, "w1", "i101.npy", "s101.json")
    rec2 = ArchiveRecord(102, "w2", "i102.npy", "s102.json")
    reg1.register(rec1, origin_id="common-origin")
    reg1.register(rec2, origin_id="common-origin")

    before_bytes = index_file.read_bytes()
    before_md5 = hashlib.md5(before_bytes).hexdigest()

    # Re-open in a fresh instance
    reg2 = WriteRegistry(index_path=str(index_file))
    assert reg2.entries == []

    # Attempt to register key 101 again (present at line 1 on disk)
    with pytest.raises(ValueError) as exc1:
        reg2.register(rec1, origin_id="common-origin")

    msg1 = str(exc1.value)
    assert "duplicate registry key" in msg1
    assert repr(("common-origin", 101)) in msg1
    assert f"at line 1 of {index_file}" in msg1
    assert "append-only index: history is never rewritten" in msg1

    # Attempt to register key 102 again (present at line 2 on disk)
    with pytest.raises(ValueError) as exc2:
        reg2.register(rec2, origin_id="common-origin")

    msg2 = str(exc2.value)
    assert "duplicate registry key" in msg2
    assert repr(("common-origin", 102)) in msg2
    assert f"at line 2 of {index_file}" in msg2

    # File and instance untouched
    after_bytes = index_file.read_bytes()
    assert after_bytes == before_bytes
    assert hashlib.md5(after_bytes).hexdigest() == before_md5
    assert reg2.entries == []


def test_l6_reopen_append_prefix_preservation(tmp_path: Path) -> None:
    """L6 re-open append + prefix preservation: new instance appends new key, preserved prefix unchanged."""
    index_file = tmp_path / "spine_index.jsonl"
    reg1 = WriteRegistry(index_path=str(index_file))

    rec1 = ArchiveRecord(1, "w", "i1.npy", "s1.json")
    rec2 = ArchiveRecord(2, "w", "i2.npy", "s2.json")
    reg1.register(rec1, origin_id="orig-prefix")
    reg1.register(rec2, origin_id="orig-prefix")

    before_bytes = index_file.read_bytes()
    before_lines = before_bytes.decode("utf-8").splitlines()
    before_digest = index_digest(before_lines)

    # Re-open
    reg2 = WriteRegistry(index_path=str(index_file))
    rec3 = ArchiveRecord(3, "w", "i3.npy", "s3.json")
    new_entry = reg2.register(rec3, origin_id="orig-prefix")

    after_bytes = index_file.read_bytes()
    expected_extra = len(entry_line(new_entry)) + 1
    assert len(after_bytes) == len(before_bytes) + expected_extra
    assert after_bytes[: len(before_bytes)] == before_bytes

    after_lines = after_bytes.decode("utf-8").splitlines()
    assert len(after_lines) == 3
    # Preserved prefix digest stability
    assert index_digest(after_lines[:2]) == before_digest

    parsed_keys = [
        (json.loads(line)["origin_id"], json.loads(line)["write_id"])
        for line in after_lines
    ]
    assert set(parsed_keys) == {("orig-prefix", 1), ("orig-prefix", 2)} | {("orig-prefix", 3)}
    assert reg2.entries == [new_entry]


def test_l7_failure_path_live(tmp_path: Path) -> None:
    """L7 failure path is live: parent path is a regular file -> OSError, entries untouched, clean recovery."""
    parent_file = tmp_path / "afile"
    parent_file.write_text("regular file", encoding="utf-8")

    impossible_path = str(parent_file / "index.jsonl")
    reg = WriteRegistry(index_path=impossible_path)

    rec = ArchiveRecord(1, "w", "img.npy", "side.json")
    with pytest.raises(OSError):
        reg.register(rec, origin_id="orig-fail")

    assert reg.entries == []
    assert not os.path.exists(impossible_path)

    # Subsequent register on valid path succeeds
    valid_path = str(tmp_path / "valid_dir" / "index.jsonl")
    reg_valid = WriteRegistry(index_path=valid_path)
    entry = reg_valid.register(rec, origin_id="orig-fail")
    assert entry.key == ("orig-fail", 1)
    assert os.path.isfile(valid_path)
    assert reg_valid.entries == [entry]


def test_l8_nowrite_refusal_and_bad_key(tmp_path: Path) -> None:
    """L8 no-write refusal + bad key: invalid origin/write_id creates no file; empty/blank log handled cleanly."""
    target_path = tmp_path / "uncreated" / "index.jsonl"
    reg = WriteRegistry(index_path=str(target_path))
    rec = ArchiveRecord(1, "w", "img.npy", "side.json")

    # Empty or whitespace origin_id raises ValueError, no file created
    for bad_origin in ("", "   ", "\t\n"):
        with pytest.raises(ValueError):
            reg.register(rec, origin_id=bad_origin)
        assert not target_path.exists()
        assert not target_path.parent.exists()
        assert reg.entries == []

    # Non-int write_id raises TypeError, no file created
    bad_rec = ArchiveRecord("not-an-int", "w", "img.npy", "side.json")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reg.register(bad_rec, origin_id="valid-origin")
    assert not target_path.exists()
    assert reg.entries == []

    # Empty (0-byte) file treated as no entries (no crash, no phantom duplicate)
    empty_file = tmp_path / "empty_index.jsonl"
    empty_file.write_bytes(b"")
    reg_empty = WriteRegistry(index_path=str(empty_file))
    e1 = reg_empty.register(rec, origin_id="clean-origin")
    assert e1.key == ("clean-origin", 1)
    assert len(empty_file.read_bytes().decode("utf-8").splitlines()) == 1

    # Trailing blank lines treated as no entries
    blank_file = tmp_path / "blank_index.jsonl"
    blank_file.write_text("\n\n   \n\t\n", encoding="utf-8")
    reg_blank = WriteRegistry(index_path=str(blank_file))
    e2 = reg_blank.register(rec, origin_id="clean-origin")
    assert e2.key == ("clean-origin", 1)


def test_l9_duplicate_refusal_via_injected_entries(tmp_path: Path) -> None:
    """L9 in-memory duplicate clause is load-bearing (R2a).

    The constructor can be handed entries that are NOT on disk (entries was, and
    still is, an injectable field). The disk scan cannot see those, so refusing
    them is the in-memory clause's whole job: refusal must fire with n == 0 and
    must still create no bytes.
    """
    target = tmp_path / "newdir" / "index.jsonl"
    rec = ArchiveRecord(77, "stage-inject", "img.npy", "side.json")

    injected = RegistryEntry(
        origin_id="inject-origin",
        write_id=77,
        writer=rec.writer,
        image_path=rec.image_path,
        line_sha=line_sha_for(rec),
        written_at=rec.written_at,
    )
    reg = WriteRegistry(index_path=str(target), entries=[injected])
    assert not target.exists()  # nothing on disk to scan

    with pytest.raises(ValueError) as excinfo:
        reg.register(rec, origin_id="inject-origin")

    msg = str(excinfo.value)
    assert "duplicate registry key" in msg
    assert repr(("inject-origin", 77)) in msg
    assert f"at line 0 of {target}" in msg
    assert "append-only index: history is never rewritten" in msg
    assert not target.exists()
    assert reg.entries == [injected]
