#!/usr/bin/env python3
"""Gate tests for D22-LEDGER-1 single append tool."""

from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys

LEDGER_ORIGINAL = ".builder_queue/DEFECT-22_arc_legA_instability.json"
TOOL_PATH = ".builder_queue/d22_ledger.py"


def test_l1_append(tmp_path: Path):
    """L1 append: a valid append call on a COPY adds a dict entry with all 8 fields populated and verdict: green; exit 0."""
    copy_path = tmp_path / "defect22_ledger.json"
    shutil.copyfile(LEDGER_ORIGINAL, copy_path)

    cmd = [
        sys.executable,
        TOOL_PATH,
        "append",
        "--ledger", str(copy_path),
        "--leg", "80",
        "--seed", "987654321",
        "--head", "fedcba9",
        "--crashes", "0",
        "--oom-kill-delta", "0",
        "--mem-peak", "1700000000",
        "--verdict", "green",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"append failed: {res.stderr}"

    with copy_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert "ledger_leg80" in data, "Expected key ledger_leg80 not found in ledger"
    entry = data["ledger_leg80"]
    assert isinstance(entry, dict), f"Expected dict result object, got {type(entry)}"

    expected_fields = ["ts", "leg", "seed", "head", "crashes", "oom_kill_delta", "mem_peak", "verdict"]
    for field in expected_fields:
        assert field in entry, f"Missing expected field: {field}"
        assert entry[field] is not None, f"Field {field} is None"

    assert len(entry) == 8, f"Expected exactly 8 fields without optional note, got {len(entry)}: {list(entry.keys())}"
    assert entry["verdict"] == "green"
    assert entry["leg"] == 80
    assert entry["seed"] == 987654321
    assert entry["head"] == "fedcba9"
    assert entry["crashes"] == 0
    assert entry["oom_kill_delta"] == 0
    assert entry["mem_peak"] == 1700000000
    # Must parse as valid ISO-8601
    parsed_ts = datetime.fromisoformat(entry["ts"])
    assert parsed_ts is not None


def test_l2_derive(tmp_path: Path):
    """L2 derive: after appends of legs n=green, n+1=green, n+2=red, n+3=green (on a copy),
    recompute yields consecutive_worker_scope_green == 1 and legs_run == baseline + 4
    (baseline = result objects already in the ledger; the copy may carry history)."""
    copy_path = tmp_path / "defect22_ledger.json"
    shutil.copyfile(LEDGER_ORIGINAL, copy_path)

    with copy_path.open("r", encoding="utf-8") as f:
        baseline = sum(
            1 for v in json.load(f).values()
            if isinstance(v, dict) and "verdict" in v and "leg" in v
        )

    legs = [
        (80, "green", "2026-09-14T14:00:00+00:00"),
        (81, "green", "2026-09-14T14:05:00+00:00"),
        (82, "red",   "2026-09-14T14:10:00+00:00"),
        (83, "green", "2026-09-14T14:15:00+00:00"),
    ]

    for leg, verdict, ts in legs:
        cmd = [
            sys.executable,
            TOOL_PATH,
            "append",
            "--ledger", str(copy_path),
            "--leg", str(leg),
            "--seed", "11111",
            "--head", "abc1234",
            "--crashes", "0" if verdict == "green" else "1",
            "--oom-kill-delta", "0",
            "--mem-peak", "1600000000",
            "--verdict", verdict,
            "--ts", ts,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"append leg {leg} failed: {res.stderr}"

    # Recompute to verify derived state
    cmd_recompute = [
        sys.executable,
        TOOL_PATH,
        "recompute",
        "--ledger", str(copy_path),
    ]
    res_recompute = subprocess.run(cmd_recompute, capture_output=True, text=True)
    assert res_recompute.returncode == 0, f"recompute failed: {res_recompute.stderr}"

    with copy_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    series_state = data.get("series_state", {})
    assert series_state.get("consecutive_worker_scope_green") == 1, (
        f"Expected consecutive_worker_scope_green == 1, got {series_state.get('consecutive_worker_scope_green')}"
    )
    assert series_state.get("legs_run") == baseline + 4, (
        f"Expected legs_run == {baseline + 4}, got {series_state.get('legs_run')}"
    )


def test_l3_refuse_unparseable_timestamp(tmp_path: Path):
    """L3 refuse: an append with timestamp 2026-09-14 13:3x (or any unparseable ts) exits nonzero and ledger bytes UNCHANGED."""
    copy_path = tmp_path / "defect22_ledger.json"
    shutil.copyfile(LEDGER_ORIGINAL, copy_path)
    before_bytes = copy_path.read_bytes()

    cmd = [
        sys.executable,
        TOOL_PATH,
        "append",
        "--ledger", str(copy_path),
        "--leg", "999",
        "--seed", "12345",
        "--head", "abcdef0",
        "--crashes", "0",
        "--oom-kill-delta", "0",
        "--mem-peak", "1600000000",
        "--verdict", "green",
        "--ts", "2026-09-14 13:3x",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode != 0, f"Expected non-zero exit code on unparseable timestamp, got {res.returncode}"

    after_bytes = copy_path.read_bytes()
    assert before_bytes == after_bytes, "Ledger file bytes changed despite refusal"


def test_l4_single_writer():
    """L4 single-writer: git ls-files '.builder_queue/append_d22_ledger*' returns no legacy scripts;
    only the single tool .builder_queue/d22_ledger.py exists."""
    # (a) Verify legacy one-shot tracked scripts are gone
    legacy_tracked = subprocess.check_output(
        ["git", "ls-files", ".builder_queue/append_d22_ledger*"],
        text=True
    ).strip().splitlines()
    assert legacy_tracked == [], f"Expected zero tracked legacy append scripts, got: {legacy_tracked}"

    # (b) Verify the single writer tool is tracked and present
    writer_tracked = subprocess.check_output(
        ["git", "ls-files", TOOL_PATH],
        text=True
    ).strip().splitlines()
    assert writer_tracked == [TOOL_PATH], f"Expected single writer {TOOL_PATH} tracked, got: {writer_tracked}"

    # (c) Verify untracked legacy one-shot scripts do not exist
    untracked_files = [
        Path(".builder_queue/append_d22_ledger.py"),
        Path(".builder_queue/append_d22_ledger_leg44.py"),
        Path(".builder_queue/append_d22_ledger_leg61.py"),
        Path(".builder_queue/append_d22_ledger_leg62.py"),
    ]
    for p in untracked_files:
        assert not p.exists(), f"Untracked legacy script {p} must be deleted"


def test_l5_idempotence(tmp_path: Path):
    """L5 idempotence: appending a leg number that already exists exits nonzero, ledger unchanged."""
    copy_path = tmp_path / "defect22_ledger.json"
    shutil.copyfile(LEDGER_ORIGINAL, copy_path)

    cmd_first = [
        sys.executable,
        TOOL_PATH,
        "append",
        "--ledger", str(copy_path),
        "--leg", "80",
        "--seed", "123",
        "--head", "abc1234",
        "--crashes", "0",
        "--oom-kill-delta", "0",
        "--mem-peak", "1600000000",
        "--verdict", "green",
    ]
    res1 = subprocess.run(cmd_first, capture_output=True, text=True)
    assert res1.returncode == 0, f"First append should succeed: {res1.stderr}"

    before_bytes = copy_path.read_bytes()

    # Second append with the same leg number
    cmd_second = [
        sys.executable,
        TOOL_PATH,
        "append",
        "--ledger", str(copy_path),
        "--leg", "80",
        "--seed", "456",
        "--head", "def5678",
        "--crashes", "0",
        "--oom-kill-delta", "0",
        "--mem-peak", "1700000000",
        "--verdict", "green",
    ]
    res2 = subprocess.run(cmd_second, capture_output=True, text=True)
    assert res2.returncode != 0, f"Duplicate leg append should exit nonzero, got {res2.returncode}"

    after_bytes = copy_path.read_bytes()
    assert before_bytes == after_bytes, "Ledger file bytes changed on duplicate append refusal"
