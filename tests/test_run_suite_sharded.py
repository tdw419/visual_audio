"""BK-18 gate: memory-bounded sharded suite runner.

The builder's execution cgroup OOM-kills a single-process full pytest run at
~4.17 GB anon-RSS (~51% of 2122 tests; 3 kernel OOM kills 2026-09-22
22:00/22:08/22:36 — see .builder_queue/RESEARCH_suite_oom_ceiling.md).
tools/run_suite_sharded.py makes "full suite status" a runnable claim:
one test file per subprocess, aggregated summary, nonzero exit on any
shard failure or kill.

Legs:
  L1  runner on a 3-file fixture subset -> exit 0; per-file counts match a
      direct pytest run of the same files.
  L2  subset containing one known-failing test -> exit 1; the failing test's
      NAME appears in the summary.
  L3  non-vacuity: a shard whose subprocess is KILLED (fixture SIGKILLs
      itself mid-run — the exact failure mode that motivated BK-18) ->
      summary marks the shard KILLED and the runner exits nonzero.
  L4  the runner never imports test modules in its own process: summary
      reports zero self-imported test modules and per-shard self-RSS is
      flat; mutation probe: a runner copy that DOES import a fixture module
      in-process is caught by the same summary line (the leg discriminates).
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "tools" / "run_suite_sharded.py"

PASSING_A = """
def test_a_one():
    assert True


def test_a_two():
    assert 1 + 1 == 2
"""

PASSING_B = """
def test_b_one():
    assert "shard"
"""

FAILING_C = """
def test_c_good():
    assert True


def test_c_bad_bk18():
    assert False, "BK-18 L2 known failure"
"""

KILL_D = """
import os
import signal


def test_d_never_reports():
    os.kill(os.getpid(), signal.SIGKILL)
"""


def _write_fixture(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def _run_runner(files, out: Path, extra=()):
    cmd = [
        sys.executable,
        str(RUNNER),
        *[str(f) for f in files],
        "--out",
        str(out),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def _counts_from_direct_pytest(files):
    """Direct single-process pytest on the same files (the L1 comparator)."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=no",
        "-p",
        "no:cacheprovider",
        *[str(f) for f in files],
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    m = re.search(r"(\d+) passed", proc.stdout)
    passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", proc.stdout)
    failed = int(m.group(1)) if m else 0
    return passed, failed, proc.returncode


def test_l1_three_file_subset_exit0_counts_match_direct_pytest(tmp_path):
    f1 = _write_fixture(tmp_path / "test_shard_a.py", PASSING_A)
    f2 = _write_fixture(tmp_path / "test_shard_b.py", PASSING_B)
    f3 = _write_fixture(tmp_path / "test_shard_c.py", PASSING_B + "\n\n\ndef test_c_two():\n    assert not None\n")  # all-pass subset
    out = tmp_path / "SUITE_RUN.md"
    proc = _run_runner([f1, f2, f3], out)
    assert proc.returncode == 0, f"runner rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert out.exists(), "summary artifact missing"
    text = out.read_text()
    # L1 comparator: direct pytest over the same files agrees on totals.
    direct_passed, direct_failed, direct_rc = _counts_from_direct_pytest([f1, f2, f3])
    assert direct_rc == 0 and direct_failed == 0
    total_passed = sum(int(m) for m in re.findall(r"^test_\S+\.py: \w+ passed=(\d+)", text, re.M))
    assert total_passed == direct_passed, (
        f"runner counted {total_passed} passed, direct pytest counted {direct_passed}"
    )
    for f in (f1, f2, f3):
        assert f.name in text, f"summary does not list shard {f.name}"
    assert "TOTAL" in text and "passed=" in text


def test_l2_known_failure_exit1_name_in_summary(tmp_path):
    f1 = _write_fixture(tmp_path / "test_shard_a.py", PASSING_A)
    fc = _write_fixture(tmp_path / "test_shard_fail.py", FAILING_C)
    out = tmp_path / "SUITE_RUN.md"
    proc = _run_runner([f1, fc], out)
    assert proc.returncode != 0, "runner exited 0 despite a failing shard"
    text = out.read_text()
    assert "test_c_bad_bk18" in text, "failing test NAME absent from summary"
    assert re.search(r"failed=1", text), "summary does not record failed=1"


def test_l3_killed_shard_marked_and_nonzero_exit(tmp_path):
    f1 = _write_fixture(tmp_path / "test_shard_a.py", PASSING_A)
    fd = _write_fixture(tmp_path / "test_shard_kill.py", KILL_D)
    out = tmp_path / "SUITE_RUN.md"
    proc = _run_runner([f1, fd], out)
    assert proc.returncode != 0, "runner exited 0 despite a KILLED shard"
    text = out.read_text()
    assert re.search(r"KILLED", text), "summary does not mark the killed shard"
    assert "test_shard_kill.py" in text


def test_l4_runner_imports_no_test_modules_rss_flat(tmp_path):
    f1 = _write_fixture(tmp_path / "test_shard_a.py", PASSING_A)
    f2 = _write_fixture(tmp_path / "test_shard_b.py", PASSING_B)
    out = tmp_path / "SUITE_RUN.md"
    proc = _run_runner([f1, f2], out)
    assert proc.returncode == 0
    text = out.read_text()
    m = re.search(r"self-imported test modules:\s*(\S+)", text)
    assert m, "summary missing self-imported-modules line"
    assert m.group(1) == "NONE", f"runner imported test modules in-process: {m.group(1)}"
    rss = [int(v) for v in re.findall(r"self_rss_kb=(\d+)", text)]
    assert len(rss) >= 2, "summary missing per-shard self-RSS samples"
    assert max(rss) - min(rss) < 100_000, f"runner RSS grew across shards: {rss}"


def test_l4_mutation_runner_that_imports_fixtures_is_caught(tmp_path):
    """Non-vacuity: corrupt a runner copy to import a fixture in-process;
    the same summary line must catch it (the L4 leg cannot pass vacuously)."""
    f1 = _write_fixture(tmp_path / "test_shard_a.py", PASSING_A)
    mutated = tmp_path / "runner_mutated.py"
    src = RUNNER.read_text()
    anchor = "from __future__ import annotations\n"
    assert anchor in src, "runner lost its future-import anchor"
    inject = (
        "import importlib.util as _iu, sys as _sys\n"
        f"_spec = _iu.spec_from_file_location('test_evil_fixture', {str(f1)!r})\n"
        "_mod = _iu.module_from_spec(_spec)\n"
        "_spec.loader.exec_module(_mod)\n"
        "_sys.modules['test_evil_fixture'] = _mod\n"
    )
    mutated.write_text(src.replace(anchor, anchor + inject, 1))
    out = tmp_path / "SUITE_RUN_MUT.md"
    cmd = [sys.executable, str(mutated), str(f1), "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0
    text = out.read_text()
    m = re.search(r"self-imported test modules:\s*(\S+)", text)
    assert m and m.group(1) != "NONE", (
        "mutated runner (in-process fixture import) was NOT caught — L4 leg is vacuous"
    )
    assert "test_evil_fixture" in m.group(1)


def test_l3_mutation_killed_shard_ignored_is_caught(tmp_path):
    """Non-vacuity: a runner copy that treats a killed shard as OK must be
    caught by the exit-code contract (L3 cannot pass vacuously)."""
    f1 = _write_fixture(tmp_path / "test_shard_a.py", PASSING_A)
    fd = _write_fixture(tmp_path / "test_shard_kill.py", KILL_D)
    mutated = tmp_path / "runner_mutated3.py"
    src = RUNNER.read_text()
    # Weaken exactly the kill classification: any rc becomes OK.
    assert "proc.returncode < 0" in src, "runner lost its kill classifier"
    mutated_src = src.replace(
        "proc.returncode < 0",
        "False and proc.returncode < 0",
    )
    assert mutated_src != src, "mutation did not apply"
    mutated.write_text(mutated_src)
    out = tmp_path / "SUITE_RUN_MUT3.md"
    cmd = [sys.executable, str(mutated), str(f1), str(fd), "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    text = out.read_text()
    # The mutated runner calls a KILLED shard OK — the gate must go RED on it
    # via the hard contract that a signal-killed subprocess can never yield rc 0.
    killed_marked = re.search(r"KILLED", text)
    assert not killed_marked or proc.returncode != 0, (
        "mutated kill classifier went undetected: shard killed but gate green"
    )
    assert proc.returncode != 0, (
        "mutated runner exited 0 on a signal-killed shard — exit contract is vacuous"
    )
