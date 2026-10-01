"""Gate tests for HARNESS-FAILNAME-1: the sweep harness must name failing tests, not just count them.

Roadmap row: HARNESS-FAILNAME-1 in systems/GLYPH_SELF_HOSTING_ROADMAP.md
Ticket: .builder_queue/TICKET_harness_failname_1.md
Gate command:
    /usr/bin/python3 -m pytest tests/test_harness_failname.py tests/test_suite_iso_harness.py tests/test_sweep_preflight.py -q
"""

import json
import os
from pathlib import Path
import pytest

from tools.suite_iso_harness import (
    TestRecord,
    run_single_file,
    run_suite_iso,
    write_record_to_sink,
    parse_failed_nodeids,
)
import tools.suite_iso_harness as harness


def test_l1_node_id_capture(tmp_path):
    """L1: node-id capture.
    Run the harness over a tmp_path synthetic file with exactly 2 failing legs
    (test_a passes, test_b and test_c fail): the record's failed_nodeids equals
    exactly ["test_b", "test_c"] (with directory and file-path prefix stripped).
    """
    f = tmp_path / "test_synth_two_fail.py"
    f.write_text(
        "def test_a():\n"
        "    assert True\n"
        "def test_b():\n"
        "    assert False, 'b failed'\n"
        "def test_c():\n"
        "    assert False, 'c failed'\n"
    )

    rec = run_single_file(str(f), timeout_s=10.0)
    assert rec.verdict == "FAIL"
    assert rec.rc != 0
    assert "failed_nodeids" in rec
    assert rec.failed_nodeids is not None
    assert isinstance(rec.failed_nodeids, list)
    # The record carries exactly the 2 failing node IDs with file-path prefix trimmed
    assert sorted(rec.failed_nodeids) == ["test_b", "test_c"]
    assert rec.failed_nodeids in (["test_b", "test_c"], ["test_c", "test_b"])
    assert rec["failed_nodeids"] == rec.failed_nodeids


def test_l2_green_file(tmp_path):
    """L2: green file.
    A tmp_path file with 2 passing legs yields failed_nodeids == [] exactly
    (not missing-key, not None — an empty list).
    """
    f = tmp_path / "test_synth_pass.py"
    f.write_text(
        "def test_pass_1():\n"
        "    assert 1 == 1\n"
        "def test_pass_2():\n"
        "    assert True\n"
    )

    rec = run_single_file(str(f), timeout_s=10.0)
    assert rec.verdict == "PASS"
    assert rec.rc == 0
    assert "failed_nodeids" in rec
    assert rec.failed_nodeids is not None
    assert rec.failed_nodeids == []
    assert rec["failed_nodeids"] == []


def test_l3_back_compat(tmp_path):
    """L3: back-compat.
    last_line is still present on every record; a --sink run's lines still
    parse as one JSON object per line (SUITE-ISO-2 contract).
    """
    f_pass = tmp_path / "test_pass.py"
    f_pass.write_text("def test_ok(): assert True\n")
    f_fail = tmp_path / "test_fail.py"
    f_fail.write_text("def test_bad(): assert False\n")
    sink_path = tmp_path / "records.jsonl"

    records = run_suite_iso(
        targets=[tmp_path],
        timeout_s=10.0,
        repo_root=tmp_path,
    )
    assert len(records) >= 2

    # Check last_line on TestRecord attribute and dict key
    for r in records:
        assert "last_line" in r
        assert hasattr(r, "last_line")
        assert isinstance(r.last_line, str)
        assert len(r.last_line) > 0
        assert "failed_nodeids" in r
        assert hasattr(r, "failed_nodeids")
        assert isinstance(r.failed_nodeids, list)

    # Check sink serialization (SUITE-ISO-2 contract)
    sink_fd = os.open(str(sink_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND, 0o644)
    try:
        for r in records:
            write_record_to_sink(sink_fd, r)
    finally:
        os.close(sink_fd)

    lines = sink_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records)
    for line in lines:
        obj = json.loads(line)
        assert isinstance(obj, dict)
        assert "last_line" in obj
        assert "failed_nodeids" in obj
        assert "verdict" in obj
        assert "counts" in obj
        assert "duration_s" in obj
        assert "path" in obj


def test_l4_non_vacuity(tmp_path, monkeypatch):
    """L4: non-vacuity falsifier.
    Monkeypatch the parse helper to return [] unconditionally and assert
    L1's scenario then FAILS the capture assertion (prove the gate can go red).

    What PASS does not prove:
    A pass here proves that L1's capture assertion is sensitive to the parser
    output (it cannot vacuously pass when parse_failed_nodeids produces an empty list).
    It does not prove that the parser handles every edge case in pytest output or all
    possible node ID formats.
    """
    f = tmp_path / "test_synth_fail.py"
    f.write_text(
        "def test_a():\n"
        "    assert True\n"
        "def test_b():\n"
        "    assert False\n"
        "def test_c():\n"
        "    assert False\n"
    )

    # Monkeypatch the parse helper to return [] unconditionally
    monkeypatch.setattr(harness, "parse_failed_nodeids", lambda *a, **kw: [])

    rec = harness.run_single_file(str(f), timeout_s=10.0)
    assert rec.verdict == "FAIL"
    assert rec.failed_nodeids == []

    # Prove L1's capture assertion FAILS under the neutered parser
    with pytest.raises(AssertionError):
        assert sorted(rec.failed_nodeids) == ["test_b", "test_c"]


def test_l5_verdict_semantics(tmp_path):
    """L5: verdict semantics.
    The failing synthetic file's verdict is still FAIL and rc != 0 (no semantic drift),
    and a TIMEOUT-classified file carries failed_nodeids == [].
    """
    # 1. Failing synthetic file has verdict == FAIL and rc != 0
    f_fail = tmp_path / "test_fail_sem.py"
    f_fail.write_text("def test_bad(): assert 1 == 2\n")
    rec_fail = run_single_file(str(f_fail), timeout_s=10.0)
    assert rec_fail.verdict == "FAIL"
    assert rec_fail.rc != 0
    assert "test_bad" in rec_fail.failed_nodeids

    # 2. TIMEOUT-classified file carries failed_nodeids == []
    f_sleep = tmp_path / "test_sleep_sem.py"
    f_sleep.write_text("import time\ndef test_sleep(): time.sleep(3)\n")
    rec_timeout = run_single_file(str(f_sleep), timeout_s=0.5, import_grace_s=10.0)
    assert rec_timeout.verdict == "TIMEOUT"
    assert "failed_nodeids" in rec_timeout
    assert rec_timeout.failed_nodeids == []
