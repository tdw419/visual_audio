"""Tests for SUITE-HEAVY-1: TIMEOUT classes carried as data + counts.observed_collected / counts.skipped.

Gate legs:
- L1: artifact completeness + closed vocabulary.
- L2: coverage of the committed sinks (asserts 7 distinct TIMEOUT paths).
- L3: coverage check discriminates (negative/non-vacuity leg).
- L4: sink really carries observed_collected and skipped fields.
- L5: non-vacuity of L4 (mutant harness missing observed_collected goes RED under assert_l4_records).
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from tools import suite_iso_harness


def test_l1_artifact_completeness_and_closed_vocabulary():
    """L1: systems/SUITE_TIMEOUT_CLASSES.json loads; every entry has required fields;
    class is in closed vocabulary; solo_seconds > 0; evidence/measured_at non-empty; path exists on disk.
    """
    assert hasattr(suite_iso_harness, "CLASS_VOCABULARY"), "CLASS_VOCABULARY missing from suite_iso_harness"
    vocab = suite_iso_harness.CLASS_VOCABULARY
    assert set(vocab) == {"BUDGET-RAISE", "CONTENTION-SENSITIVE", "RESTRUCTURE", "KNOWN-INPUT"}

    artifact_path = Path("systems/SUITE_TIMEOUT_CLASSES.json")
    assert artifact_path.is_file(), f"{artifact_path} is missing"

    assert hasattr(suite_iso_harness, "load_timeout_classes"), "load_timeout_classes missing from suite_iso_harness"
    data = suite_iso_harness.load_timeout_classes(artifact_path)

    entries = data.get("entries", [])
    assert len(entries) >= 8, f"Expected at least 8 entries, got {len(entries)}"

    required_keys = {"path", "class", "solo_seconds", "solo_command", "in_sink", "evidence", "measured_at"}
    for entry in entries:
        missing = required_keys - set(entry.keys())
        assert not missing, f"Entry for {entry.get('path')} missing keys: {missing}"
        assert entry["class"] in vocab, f"Unknown class {entry['class']} in {entry['path']}"
        assert isinstance(entry["solo_seconds"], (int, float)) and entry["solo_seconds"] > 0, (
            f"Invalid solo_seconds in {entry}"
        )
        assert isinstance(entry["in_sink"], bool), f"in_sink must be bool in {entry}"
        assert isinstance(entry["evidence"], str) and len(entry["evidence"].strip()) > 0, (
            f"Empty evidence in {entry}"
        )
        assert isinstance(entry["measured_at"], str) and len(entry["measured_at"].strip()) > 0, (
            f"Empty measured_at in {entry}"
        )
        assert Path(entry["path"]).is_file(), f"Path does not exist on disk: {entry['path']}"


def test_l2_coverage_of_committed_sinks():
    """L2: For every record with verdict == 'TIMEOUT' in the committed sinks, the path has an entry.
    Asserts the TIMEOUT set is non-empty (7 distinct paths).
    """
    sinks = [
        Path("output/SUITE_BASE1_LOCK_SINK.jsonl"),
        Path("output/SUITE_DEFECT27_SINK.jsonl"),
        Path("output/SUITE_DEFECT28F3_SINK.jsonl"),
    ]
    timeout_records = []
    timeout_paths = set()
    for s in sinks:
        if s.is_file():
            for line in s.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("verdict") == "TIMEOUT":
                    timeout_records.append(r)
                    timeout_paths.add(r["path"])

    assert len(timeout_paths) == 7, (
        f"Expected 7 distinct TIMEOUT paths in committed sinks, got {len(timeout_paths)}: {sorted(timeout_paths)}"
    )

    data = suite_iso_harness.load_timeout_classes()
    unclassified = suite_iso_harness.unclassified_timeouts(timeout_records, data)
    assert unclassified == [], f"Found unclassified timeouts: {unclassified}"


def test_l3_coverage_check_discriminates():
    """L3: Feeding unclassified_timeouts a synthetic record with unclassified TIMEOUT returns that path;
    feeding it a classified path returns []. Unknown class tokens in artifact are reported as violations.
    """
    data = suite_iso_harness.load_timeout_classes()

    # 1. Unclassified path returns that path
    synthetic_unclassified = [{"path": "tests/test_unclassified_synthetic_file.py", "verdict": "TIMEOUT"}]
    res = suite_iso_harness.unclassified_timeouts(synthetic_unclassified, data)
    assert res == ["tests/test_unclassified_synthetic_file.py"]

    # 2. Classified path returns []
    synthetic_classified = [{"path": "tests/test_probe_stval.py", "verdict": "TIMEOUT"}]
    res2 = suite_iso_harness.unclassified_timeouts(synthetic_classified, data)
    assert res2 == []

    # 3. Non-timeout record is ignored even if unclassified
    synthetic_pass = [{"path": "tests/test_unclassified_synthetic_file.py", "verdict": "PASS"}]
    res3 = suite_iso_harness.unclassified_timeouts(synthetic_pass, data)
    assert res3 == []

    # 4. Unknown class token in artifact is reported as violation (raises ValueError)
    bad_data = {
        "entries": [
            {
                "path": "tests/test_probe_stval.py",
                "class": "UNKNOWN-CLASS-TOKEN",
            }
        ]
    }
    with pytest.raises(ValueError) as excinfo:
        suite_iso_harness.unclassified_timeouts(synthetic_classified, bad_data)
    assert "UNKNOWN-CLASS-TOKEN" in str(excinfo.value)


def assert_l4_records(records):
    """Assertion helper for L4 records and L5 non-vacuity check."""
    assert len(records) == 3, f"Expected 3 records, got {len(records)}"
    for r in records:
        counts = r.get("counts", {})
        assert "observed_collected" in counts, f"Missing observed_collected in {r['path']}: {counts}"
        assert "skipped" in counts, f"Missing skipped in {r['path']}: {counts}"
        assert isinstance(counts["observed_collected"], int), f"observed_collected not int in {r['path']}"
        assert isinstance(counts["skipped"], int), f"skipped not int in {r['path']}"

    by_name = {Path(r["path"]).name: r for r in records}
    assert by_name["test_pass.py"]["verdict"] == "PASS"
    assert by_name["test_pass.py"]["counts"]["passed"] >= 1
    assert by_name["test_pass.py"]["counts"]["observed_collected"] >= 1

    assert by_name["test_skip.py"]["verdict"] == "PASS"
    assert by_name["test_skip.py"]["counts"]["skipped"] >= 1
    assert by_name["test_skip.py"]["counts"]["observed_collected"] >= 1

    assert by_name["test_sleep.py"]["verdict"] == "TIMEOUT"
    assert by_name["test_sleep.py"]["counts"]["observed_collected"] > 0


def test_l4_sink_really_carries_fields(tmp_path):
    """L4: Run harness CLI as subprocess over tmp_path holding passing, skipping, and sleeping files;
    assert every emitted record carries observed_collected and skipped, TIMEOUT observed_collected > 0,
    and skipping reports skipped >= 1.
    """
    (tmp_path / "test_pass.py").write_text("def test_ok(): assert True\n")
    (tmp_path / "test_skip.py").write_text(
        "import pytest\n@pytest.mark.skip(reason='testing skipped')\ndef test_s(): pass\n"
    )
    (tmp_path / "test_sleep.py").write_text("import time\ndef test_s(): time.sleep(10)\n")

    sink = tmp_path / "sink.jsonl"
    harness_path = Path("tools/suite_iso_harness.py").resolve()

    proc = subprocess.run(
        [
            sys.executable,
            str(harness_path),
            str(tmp_path),
            "-t",
            "1.5",
            "--sink",
            str(sink),
            "-w",
            "1",
        ],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert sink.is_file(), f"Sink file was not created: {sink}"
    lines = [ln for ln in sink.read_text().splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]
    assert_l4_records(records)


def test_l5_non_vacuity_of_l4(tmp_path):
    """L5: Re-run against a temp copy of the harness with observed_collected removed;
    assert assert_l4_records raises AssertionError. Verify real harness md5 before == after.
    """
    harness_path = Path("tools/suite_iso_harness.py").resolve()
    harness_bytes = harness_path.read_bytes()
    md5_before = hashlib.md5(harness_bytes).hexdigest()
    print(f"harness md5 before: {md5_before}")

    harness_text = harness_bytes.decode("utf-8")
    assert '"observed_collected":' in harness_text, "Harness does not contain observed_collected"

    # Mutate harness copy by removing observed_collected from counts dicts
    mutant_text = harness_text.replace('"observed_collected": observed_collected,', "")
    mutant_text = mutant_text.replace('"observed_collected": observed,', "")
    mutant_text = mutant_text.replace('"observed_collected": 0,', "")

    mutant_harness = tmp_path / "mutant_harness_not_a_test.py"
    mutant_harness.write_text(mutant_text)

    # Set up test files
    test_dir = tmp_path / "tests_dir"
    test_dir.mkdir()
    (test_dir / "test_pass.py").write_text("def test_ok(): assert True\n")
    (test_dir / "test_skip.py").write_text(
        "import pytest\n@pytest.mark.skip(reason='testing skipped')\ndef test_s(): pass\n"
    )
    (test_dir / "test_sleep.py").write_text("import time\ndef test_s(): time.sleep(10)\n")

    sink = tmp_path / "mutant_sink.jsonl"
    proc = subprocess.run(
        [
            sys.executable,
            str(mutant_harness),
            str(test_dir),
            "-t",
            "1.5",
            "--sink",
            str(sink),
            "-w",
            "1",
        ],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert sink.is_file()
    lines = [ln for ln in sink.read_text().splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]

    with pytest.raises(AssertionError) as excinfo:
        assert_l4_records(records)
    print(f"L5 non-vacuity confirmed: assert_l4_records raised {excinfo.value}")

    md5_after = hashlib.md5(harness_path.read_bytes()).hexdigest()
    print(f"harness md5 after: {md5_after}")
    assert md5_before == md5_after, f"Real harness was modified! {md5_before} != {md5_after}"
