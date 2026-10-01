"""Gate tests for SUITE-ISO-1: per-file isolation harness.

Roadmap row: SUITE-ISO-1 in systems/GLYPH_SELF_HOSTING_ROADMAP.md
Gate command:
    /usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q
"""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# The deliverable under test
from tools.suite_iso_harness import (
    TestRecord,
    discover_test_files,
    run_single_file,
    run_suite_iso,
    compute_exit_code,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_l1_per_file_verdicts():
    """L1: The runner executes each file in its own subprocess and emits
    machine-readable records with path, verdict in {PASS,FAIL,CRASH,TIMEOUT,ERROR},
    duration_s, rc, counts (collected/passed/failed), and last non-empty line.
    Harness exit code is non-zero iff any file is FAIL or CRASH.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # 1. Synthetic PASS file
        pass_file = tmp_path / "test_pass.py"
        pass_file.write_text("def test_ok(): assert 1 == 1\n")

        # 2. Synthetic FAIL file
        fail_file = tmp_path / "test_fail.py"
        fail_file.write_text("def test_bad(): assert 1 == 2, 'intentional fail'\n")

        # 3. Synthetic CRASH file (SIGSEGV)
        crash_file = tmp_path / "test_crash.py"
        crash_file.write_text(
            "import os, signal\n"
            "def test_segv():\n"
            "    os.kill(os.getpid(), signal.SIGSEGV)\n"
        )

        # 4. Synthetic ERROR file (syntax / import error)
        error_file = tmp_path / "test_error.py"
        error_file.write_text("import _definitely_nonexistent_module_xyz_12345\n")

        # Run each file individually and inspect records
        rec_pass = run_single_file(str(pass_file), timeout_s=10.0)
        assert rec_pass["verdict"] == "PASS"
        assert rec_pass["rc"] == 0
        assert rec_pass["counts"]["passed"] == 1
        assert rec_pass["counts"]["failed"] == 0
        assert rec_pass["counts"]["collected"] >= 1
        assert rec_pass["duration_s"] > 0
        assert len(rec_pass["last_line"]) > 0

        rec_fail = run_single_file(str(fail_file), timeout_s=10.0)
        assert rec_fail["verdict"] == "FAIL"
        assert rec_fail["rc"] != 0
        assert rec_fail["counts"]["failed"] >= 1
        assert rec_fail["duration_s"] > 0
        assert len(rec_fail["last_line"]) > 0

        rec_crash = run_single_file(str(crash_file), timeout_s=10.0)
        assert rec_crash["verdict"] == "CRASH"
        assert rec_crash["rc"] in (-signal.SIGSEGV, 128 + signal.SIGSEGV)
        assert rec_crash["duration_s"] > 0

        rec_error = run_single_file(str(error_file), timeout_s=10.0)
        assert rec_error["verdict"] == "ERROR"
        assert rec_error["rc"] != 0
        assert rec_error["duration_s"] > 0

        # Exit code contract
        assert compute_exit_code([rec_pass]) == 0
        assert compute_exit_code([rec_fail]) != 0
        assert compute_exit_code([rec_crash]) != 0
        assert compute_exit_code([rec_pass, rec_fail]) != 0


def test_l2_bounded_coverage_tests_root():
    """L2: Over tests/: sum of per-file collected counts equals the count from
    /usr/bin/python3 -m pytest tests/ --collect-only -q (re-measured live),
    and the sweep reaches the end of its file list inside stated budget.
    """
    # 1. Live measurement of pytest collection count over tests/
    live_res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    m = re.search(r"(\d+)\s+tests?\s+collected", live_res.stdout)
    assert m, f"Could not parse collected count from:\n{live_res.stdout}"
    expected_collected = int(m.group(1))
    assert expected_collected > 0

    # 2. Run harness over tests/ with collect_only=True and wall-clock budget
    budget_s = 60.0  # Measured parallel sweep finishes in ~22s
    start = time.perf_counter()
    records = run_suite_iso(
        targets=["tests"],
        timeout_s=15.0,
        collect_only=True,
        workers=16,
        repo_root=REPO_ROOT,
    )
    elapsed = time.perf_counter() - start

    assert elapsed <= budget_s, (
        f"Sweep over tests/ exceeded budget: {elapsed:.2f}s > {budget_s:.2f}s"
    )
    assert len(records) > 0

    sum_collected = sum(r["counts"]["collected"] for r in records)
    assert sum_collected == expected_collected, (
        f"Collected count mismatch: harness sum={sum_collected} vs live={expected_collected}"
    )


def test_l2_known_hangers_timeout():
    """L2: Over tools/ + systems/: the three known non-terminating files
    (systems/infinite_map_rs/test_daemon.py, tools/boot_alpine_opensbi_test.py, tools/test_setup_vm.py)
    MUST come back as TIMEOUT with the budget named in the record — never as a hung sweep.
    """
    hangers = [
        "systems/infinite_map_rs/test_daemon.py",
        "tools/boot_alpine_opensbi_test.py",
        "tools/test_setup_vm.py",
    ]

    per_file_timeout = 3.0
    wall_clock_budget = 20.0  # 3 files x 3s plus margin

    start = time.perf_counter()
    records = run_suite_iso(
        targets=[str(REPO_ROOT / h) for h in hangers],
        timeout_s=per_file_timeout,
        collect_only=False,
        workers=3,
        repo_root=REPO_ROOT,
    )
    elapsed = time.perf_counter() - start

    assert elapsed <= wall_clock_budget, (
        f"Hanger sweep hung or exceeded budget: {elapsed:.2f}s > {wall_clock_budget:.2f}s"
    )
    assert len(records) == 3

    for r in records:
        assert r["verdict"] == "TIMEOUT", (
            f"Expected TIMEOUT for {r['path']}, got {r['verdict']} (rc={r['rc']})"
        )
        assert r["timeout_s"] == per_file_timeout, (
            f"Budget not named in record: {r.get('timeout_s')} != {per_file_timeout}"
        )
        assert f"{per_file_timeout:.1f}s" in r["last_line"] or r["timeout_s"] == per_file_timeout


def test_l3_negative_non_vacuity_legs():
    """L3: A synthetic always-hanging file MUST report TIMEOUT and a synthetic
    failing file MUST report FAIL, each with a non-zero harness exit code,
    each inside the budget. Synthetics written into a tempdir, not tests/.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Hanging synthetic
        hang_file = tmp_path / "test_hanging.py"
        hang_file.write_text(
            "import time\n"
            "def test_infinite_loop():\n"
            "    while True:\n"
            "        time.sleep(0.1)\n"
        )

        hang_timeout = 2.0
        start = time.perf_counter()
        hang_records = run_suite_iso(
            targets=[str(hang_file)],
            timeout_s=hang_timeout,
            workers=1,
        )
        hang_elapsed = time.perf_counter() - start

        assert len(hang_records) == 1
        h_rec = hang_records[0]
        assert h_rec["verdict"] == "TIMEOUT"
        assert h_rec["timeout_s"] == hang_timeout
        assert hang_elapsed <= hang_timeout + 3.0  # inside budget
        assert compute_exit_code(hang_records) != 0

        # Failing synthetic
        fail_file = tmp_path / "test_failure.py"
        fail_file.write_text(
            "def test_will_fail():\n"
            "    assert False, 'forced failure probe'\n"
        )

        fail_timeout = 5.0
        start = time.perf_counter()
        fail_records = run_suite_iso(
            targets=[str(fail_file)],
            timeout_s=fail_timeout,
            workers=1,
        )
        fail_elapsed = time.perf_counter() - start

        assert len(fail_records) == 1
        f_rec = fail_records[0]
        assert f_rec["verdict"] == "FAIL"
        assert f_rec["counts"]["failed"] >= 1
        assert fail_elapsed <= fail_timeout
        assert compute_exit_code(fail_records) != 0


def test_l4_self_exclusion_clause():
    """L4: No file added under tests/ may be collected as a real test by
    a plain pytest tests/ (other than this gate module itself).
    No fixtures or scratch test files left in tests/.
    """
    # Verify no stray temporary files in tests/
    stray = [
        f for f in (REPO_ROOT / "tests").glob("test_*")
        if "iso_harness" in f.name and f.name != "test_suite_iso_harness.py"
    ]
    assert len(stray) == 0, f"Found stray test files in tests/: {stray}"


def test_l5_sink_survives_kill():
    """L5 (SUITE-ISO-2): a verdict already reported must survive an abnormal kill.

    Pre-fix RED (measured 2026-09-13 11:4x by the orchestrator, out of tree): the
    same experiment in `--json` mode with NO sink left `stdout_bytes=0` after a
    SIGKILL at 30 s, even though a record had already completed internally —
    records were buffered and printed only at exit. The property under test is
    mid-run growth of the sink: it is asserted while the sweep is still running,
    because a sink written only at exit would pass a naive end-of-run check.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for name in ("test_slow_a.py", "test_slow_b.py"):
            (tmp / name).write_text(
                "import time\n\n\ndef test_slow():\n    time.sleep(25)\n"
            )

        sink = tmp / "records.jsonl"
        harness = REPO_ROOT / "tools" / "suite_iso_harness.py"
        proc = subprocess.Popen(
            [sys.executable, str(harness), tmpdir, "--sink", str(sink), "-t", "60", "-w", "1"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,
        )
        mid_run_records = []
        try:
            deadline = time.time() + 45.0
            while time.time() < deadline:
                if sink.exists():
                    raw = sink.read_bytes()
                    if raw.endswith(b"\n"):
                        parsed = [
                            json.loads(x) for x in raw.split(b"\n") if x.strip()
                        ]
                        if parsed:
                            mid_run_records = parsed
                            break
                time.sleep(0.5)

            assert mid_run_records, (
                "L5: no complete record appeared in the sink while the sweep was still "
                "running — the sink is not incremental"
            )
            for key in ("path", "verdict", "duration_s", "rc", "counts", "last_line"):
                assert key in mid_run_records[0], f"L5: sink record missing key {key}"
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            if proc.stdout:
                proc.stdout.close()

        # After the abnormal kill the records must still be on disk, un-torn.
        raw = sink.read_bytes()
        assert raw.endswith(b"\n"), "L5: sink does not end with a newline (torn record)"
        lines = [x for x in raw.split(b"\n") if x.strip()]
        assert len(lines) >= 1, "L5: sink lost every record to the kill"
        for line in lines:
            json.loads(line)  # every complete line parses


def test_l6_json_contract_and_inert_sink():
    """L6 (SUITE-ISO-2): `--json` stdout is unchanged (exactly one JSON array) and
    no sink file is created when the flag is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "test_two.py").write_text(
            "def test_a():\n    assert True\n\n\ndef test_b():\n    assert True\n"
        )

        harness = REPO_ROOT / "tools" / "suite_iso_harness.py"
        proc = subprocess.run(
            [sys.executable, str(harness), tmpdir, "--json", "-t", "30", "-w", "1"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout[-500:] + proc.stderr[-500:]

        data = json.loads(proc.stdout)  # one JSON value, nothing else, on stdout
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["verdict"] == "PASS"
        assert not list(Path(tmpdir).glob("*.jsonl")), "L6: sink created without --sink"


# ---------------------------------------------------------------------------
# SWEEP-OOM-ACCT-1 — RULING_worker_memory_containment.md §(c):
#   "fail-fast on the first OOM-kill, and skip-and-record — an OOM-killed file is
#    NEVER counted as pass or fail."
# Pre-fix exposure (measured by the orchestrator against the pinned pre-fix harness,
# output/sweep_oom_acct1_orch_RED_prefix.txt): a SIGKILL child was recorded
# CRASH with counts {'collected': 0, 'passed': 0, 'failed': 1}, the string SIGKILL
# appeared nowhere in the record, and a 3-file sweep with a kill in the middle
# reported ['PASS', 'CRASH', 'PASS'] — no SKIPPED, no stop.
# ---------------------------------------------------------------------------

PREFIX_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "suite_iso_harness_prefix_d2254ea7a6a4.py"
PREFIX_SHA256 = "d2254ea7a6a46d66c4a893eb48f519f55e206b3fe5853d512459e4c60dd48351"
HARNESS = Path(os.environ.get("SUITE_ISO_HARNESS_BIN", str(REPO_ROOT / "tools" / "suite_iso_harness.py")))

DIE_SIGKILL = "import os, signal\n\n\ndef test_die():\n    os.kill(os.getpid(), signal.SIGKILL)\n"
DIE_SIGSEGV = "import os, signal\n\n\ndef test_segv():\n    os.kill(os.getpid(), signal.SIGSEGV)\n"


def _load_module_from(path, name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_l7_signal_death_is_oom_never_pass_or_fail():
    """L7 (SWEEP-OOM-ACCT-1): a child killed by SIGKILL (the cgroup OOM killer's signal) is
    recorded with the distinct verdict OOM, its counts are all-zero — never pass, never fail —
    its signal is named in the record, and it is read back from the record FILE, not prose.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # (a)-(d) unit level
        die = tmp / "test_die.py"
        die.write_text(DIE_SIGKILL)
        rec = run_single_file(str(die), timeout_s=20.0)
        assert rec["verdict"] == "OOM", f"L7: SIGKILL child recorded {rec['verdict']!r}"
        # SUITE-HEAVY-1: the two counts are now distinguishable — `collected` stays 0 because no
        # junitxml exists after a SIGKILL (no authoritative count), while `observed_collected` is 1
        # because the child DID print its collection before it died. The guard this leg has always
        # made — a kill is neither pass nor fail — is unchanged: passed and failed stay 0.
        assert rec["counts"] == {
            "collected": 0,
            "passed": 0,
            "failed": 0,
            "observed_collected": 1,
            "skipped": 0,
        }, (f"L7: an OOM-killed file must be neither pass nor fail, got {rec['counts']}")
        assert "SIGKILL" in json.dumps(rec), "L7: the record does not name the killing signal"
        assert compute_exit_code([rec]) != 0, "L7: an OOM record must not exit 0"

        # (e) end-to-end, asserted from the sink (the record file), not from stdout prose
        (tmp / "test_a_pass.py").write_text("def test_ok(): assert 1 == 1\n")
        sink = tmp / "sink.jsonl"
        proc = subprocess.run(
            [sys.executable, str(HARNESS), tmpdir, "--sink", str(sink), "-t", "20", "-w", "1"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert proc.returncode != 0, "L7: a sweep containing an OOM record exited 0"
        lines = [ln for ln in sink.read_text().splitlines() if ln.strip()]
        assert lines, "L7: no record reached the sink"
        records = [json.loads(ln) for ln in lines]  # every line parses
        by_name = {Path(r["path"]).name: r for r in records}
        assert by_name["test_die.py"]["verdict"] == "OOM"
        assert by_name["test_die.py"]["counts"]["failed"] == 0, (
            "L7: the OOM-killed file was counted as a failure"
        )
        assert by_name["test_a_pass.py"]["verdict"] == "PASS", (
            "L7: an unrelated passing file must stay PASS"
        )


def test_l8_oom_does_not_swallow_real_verdicts():
    """L8 (SWEEP-OOM-ACCT-1): non-vacuity. The new token must not swallow real outcomes:
    an ordinary failure stays FAIL, a SIGSEGV stays CRASH — and both assertions are produced by
    the classifier, not by luck (a mutant that calls every signal death OOM must disagree).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # (a) Durable RED: the PINNED pre-fix harness must exhibit the bug this row fixes.
        import hashlib

        digest = hashlib.sha256(PREFIX_FIXTURE.read_bytes()).hexdigest()
        assert digest == PREFIX_SHA256, (
            f"L8: the pinned pre-fix harness was edited (sha256 {digest}) — it must stay the "
            f"verbatim pre-fix blob so the RED below is real"
        )
        prefix = _load_module_from(PREFIX_FIXTURE, "suite_iso_harness_prefix_pin")
        die = tmp / "test_die.py"
        die.write_text(DIE_SIGKILL)
        old_rec = prefix.run_single_file(str(die), timeout_s=20.0)
        assert old_rec["verdict"] == "CRASH", (
            f"L8: pre-fix harness no longer shows the bug (got {old_rec['verdict']!r}) — "
            f"re-pin or delete this leg; do not weaken it"
        )
        assert old_rec["counts"]["failed"] == 1, "L8: pre-fix harness no longer counts the kill as a fail"

        # (b) real verdicts survive on the current harness
        segv = tmp / "test_segv.py"
        segv.write_text(DIE_SIGSEGV)
        fail = tmp / "test_fail.py"
        fail.write_text("def test_bad(): assert 1 == 2, 'intentional'\n")
        assert run_single_file(str(segv), timeout_s=20.0)["verdict"] == "CRASH", (
            "L8: SIGSEGV must stay CRASH (L1 does not weaken)"
        )
        assert run_single_file(str(fail), timeout_s=20.0)["verdict"] == "FAIL"

        # (c) discrimination: a mutant that maps EVERY signal death to OOM must be caught
        src = HARNESS.read_text()
        old_line = '    if signum == signal.SIGKILL:\n        return "SIGKILL"'
        assert src.count(old_line) == 1, (
            "L8: the OOM classifier line moved — update this mutant, do not drop the leg"
        )
        mutant = tmp / "mutant_harness.py"
        mutant.write_text(src.replace(old_line, "    if signum is not None:\n        return \"SIGKILL\""))
        mutant_mod = _load_module_from(mutant, "mutant_suite_iso_harness")
        mutant_rec = mutant_mod.run_single_file(str(segv), timeout_s=20.0)
        assert mutant_rec["verdict"] == "OOM", (
            "L8: the mutant did not mislabel SIGSEGV — L7's OOM assertion is therefore not "
            "proving what it claims"
        )


def test_l9_first_oom_stops_the_sweep_and_truncation_is_not_green():
    """L9 (SWEEP-OOM-ACCT-1): fail-fast + skip-and-record. After the first OOM kill no further
    file is launched; each un-launched file is recorded SKIPPED with all-zero counts (never PASS),
    and the truncated sweep exits non-zero. The control run proves the stop flag does not misfire.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "test_a_pass.py").write_text("def test_ok(): assert 1 == 1\n")
        (tmp / "test_m_die.py").write_text(DIE_SIGKILL)
        (tmp / "test_z_pass.py").write_text("def test_ok(): assert 1 == 1\n")

        sink = tmp / "records.jsonl"
        proc = subprocess.run(
            [sys.executable, str(HARNESS), tmpdir, "--sink", str(sink), "-t", "20", "-w", "1"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        records = [json.loads(ln) for ln in sink.read_text().splitlines() if ln.strip()]
        by_name = {Path(r["path"]).name: r for r in records}

        assert by_name["test_a_pass.py"]["verdict"] == "PASS"
        assert by_name["test_m_die.py"]["verdict"] == "OOM"
        assert "test_z_pass.py" in by_name, (
            "L9: the un-launched file was not recorded at all (skip-and-record requires a record)"
        )
        skipped = by_name["test_z_pass.py"]
        assert skipped["verdict"] == "SKIPPED", (
            f"L9: after an OOM kill the remaining file must be SKIPPED, got {skipped['verdict']!r}"
        )
        assert skipped["counts"] == {
            "collected": 0,
            "passed": 0,
            "failed": 0,
            "observed_collected": 0,
            "skipped": 0,
        }, (f"L9: a SKIPPED file must be neither pass nor fail, got {skipped['counts']}")
        assert proc.returncode != 0, "L9: a truncated sweep must not look green"
        assert "OOM: 1" in proc.stdout and "SKIPPED: 1" in proc.stdout, (
            f"L9: the verdict summary must name the truncation; got {proc.stdout[-300:]!r}"
        )

        # Control: same 3 files, no kill — the stop flag must not misfire.
        (tmp / "test_m_die.py").write_text("def test_ok(): assert 1 == 1\n")
        sink2 = tmp / "records2.jsonl"
        proc2 = subprocess.run(
            [sys.executable, str(HARNESS), tmpdir, "--sink", str(sink2), "-t", "20", "-w", "1"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        recs2 = [json.loads(ln) for ln in sink2.read_text().splitlines() if ln.strip()]
        assert [r["verdict"] for r in recs2] == ["PASS", "PASS", "PASS"], (
            f"L9 control: unexpected verdicts {[r['verdict'] for r in recs2]}"
        )
        assert proc2.returncode == 0, "L9 control: a clean sweep must exit 0"
        assert "SKIPPED" not in proc2.stdout and "OOM" not in proc2.stdout


# ---------------------------------------------------------------------------
# SUITE-COLLECT-1 — roadmap row systems/GLYPH_SELF_HOSTING_ROADMAP.md:356:
#   a file that hangs BEFORE pytest collects anything (coll=0) must get its own verdict
#   (COLLECT-HANG) instead of being folded into TIMEOUT, because the two need opposite fixes.
# Pre-fix exposure (orchestrator, HEAD d3e6513, output/COLLECT1_RED_pre_fix.json): a module-level
# `time.sleep(30)` file was recorded TIMEOUT at the FULL budget with coll=0 — identical to an
# execution overrun. Real instance (pre-fix, output/COLLECT1_xv6_pre_fix.json):
# tests/test_xv6_boot_regression.py -> TIMEOUT dur=90.1 coll=0 rc=-9.
# ---------------------------------------------------------------------------

HANG_ON_IMPORT = "import time\ntime.sleep(30)\n\n\ndef test_ok():\n    assert True\n"
SLOW_BODY_6S = "import time\n\n\ndef test_body():\n    time.sleep(6)\n    assert True\n"
RAISES_ON_IMPORT = 'raise RuntimeError("boom")\n'


def _sweep(tmpdir, extra, sink=None):
    cmd = [sys.executable, str(HARNESS), str(tmpdir)] + list(extra)
    if sink is not None:
        cmd += ["--sink", str(sink)]
    proc = subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180
    )
    records = []
    if sink is not None and Path(sink).exists():
        records = [json.loads(l) for l in Path(sink).read_text().splitlines() if l.strip()]
    return proc, records


def test_l10_collect_hang_is_a_distinct_verdict():
    """L10 (SUITE-COLLECT-1): a file that produces NO pytest output hangs BEFORE collection, so it
    is classified COLLECT-HANG, killed at the import grace (not at its budget), recorded with
    coll=0, and the sweep exits non-zero. The same sweep must NOT misfire on a file that does
    collect and then runs longer than the grace, and must not read a raising import as a hang.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "test_a_hang_import.py").write_text(HANG_ON_IMPORT)
        (tmp / "test_b_slow_body.py").write_text(SLOW_BODY_6S)
        (tmp / "test_c_raises_import.py").write_text(RAISES_ON_IMPORT)
        sink = tmp / "records.jsonl"

        proc, records = _sweep(tmpdir, ["-t", "20", "--import-grace", "3", "-w", "1"], sink)
        by_name = {Path(r["path"]).name: r for r in records}

        hang = by_name["test_a_hang_import.py"]
        assert hang["verdict"] == "COLLECT-HANG", (
            f"L10: a pre-collection hang must be its own verdict, got {hang['verdict']!r}"
        )
        assert hang["counts"] == {
            "collected": 0,
            "passed": 0,
            "failed": 0,
            "observed_collected": 0,
            "skipped": 0,
        }
        assert 2.0 <= hang["duration_s"] < 12.0, (
            f"L10: it must be killed at the grace, not at the 20s budget; "
            f"dur={hang['duration_s']:.2f}s"
        )
        assert "import grace" in hang["last_line"], (
            f"L10: the record must name the grace it was killed at; got {hang['last_line']!r}"
        )
        assert proc.returncode != 0, "L10: a COLLECT-HANG sweep must not look green"
        assert "COLLECT-HANG: 1" in proc.stdout, (
            f"L10: the summary must name the verdict; got {proc.stdout[-200:]!r}"
        )

        # (a) discrimination — the file DOES collect and then outruns the grace: not a hang.
        body = by_name["test_b_slow_body.py"]
        assert body["verdict"] == "PASS", (
            "L10: the grace must not misfire on a long-running test body — the `collected N item` "
            f"line was on the wire; got {body['verdict']!r}"
        )
        # (b) a raising import exits by itself: a loud failure, not a hang.
        raises = by_name["test_c_raises_import.py"]
        assert raises["verdict"] != "COLLECT-HANG", (
            f"L10: an import that RAISES must not be read as a hang, got {raises['verdict']!r}"
        )

        # (c) ordering rule — grace >= budget keeps the pre-existing wall-clock behaviour.
        _, records2 = _sweep(
            tmpdir, ["-t", "8", "--import-grace", "90", "-w", "1"], tmp / "records2.jsonl"
        )
        by2 = {Path(r["path"]).name: r for r in records2}
        assert by2["test_a_hang_import.py"]["verdict"] == "TIMEOUT", (
            "L10: with --import-grace >= --timeout the wall-clock budget must govern unchanged, "
            f"got {by2['test_a_hang_import.py']['verdict']!r}"
        )


def test_l11_collect_evidence_is_load_bearing():
    """L11 (non-vacuity): force the collection-evidence predicate to False in a MUTANT copy of the
    harness. The long-body file (which really does collect) must then be misread as COLLECT-HANG.
    If the mutant still classifies it correctly, L10's PASS assertion proves nothing about evidence
    having been read, and the leg is decoration.
    """
    import hashlib

    src = HARNESS.read_text()
    needle = 'return bool(_COLLECT_EVIDENCE.search(text or ""))'
    assert needle in src, (
        "L11: the evidence predicate moved — update this leg's needle, do not delete the leg"
    )
    before = hashlib.sha256(HARNESS.read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        mutant = tmp / "harness_mutant_not_a_test.py"
        mutant.write_text(src.replace(needle, "return False"))
        (tmp / "test_b_slow_body.py").write_text(SLOW_BODY_6S)

        proc = subprocess.run(
            [
                sys.executable,
                str(mutant),
                str(tmpdir),
                "-t",
                "20",
                "--import-grace",
                "3",
                "-w",
                "1",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert "COLLECT-HANG" in proc.stdout, (
            "L11: the mutant classified the collecting file correctly — the evidence predicate is "
            "not load-bearing, so L10 proves nothing. stdout tail: " + proc.stdout[-300:]
        )

    after = hashlib.sha256(HARNESS.read_bytes()).hexdigest()
    assert before == after, "L11: this leg must not modify the repo harness"


def test_l12_per_file_budget_override():
    """L12 (SUITE-COLLECT-1): `--budget PATH=SECONDS` is per-file, is reported in the record, and
    is loud when malformed or unmatched. Two identical 6-second-body files under `-t 3`: only the
    named one survives.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        budgeted = tmp / "test_a_budgeted.py"
        unbudgeted = tmp / "test_b_unbudgeted.py"
        budgeted.write_text(SLOW_BODY_6S)
        unbudgeted.write_text(SLOW_BODY_6S)
        sink = tmp / "records.jsonl"

        proc, records = _sweep(
            tmpdir,
            ["-t", "3", "--import-grace", "2", "--budget", f"{budgeted}=12", "-w", "1"],
            sink,
        )
        by_name = {Path(r["path"]).name: r for r in records}

        assert by_name["test_a_budgeted.py"]["verdict"] == "PASS", (
            f"L12: the named file must get its own 12s budget; got "
            f"{by_name['test_a_budgeted.py']['verdict']!r}"
        )
        assert by_name["test_a_budgeted.py"]["timeout_s"] == 12.0, (
            "L12: the resolved per-file budget must be reported in the record, got "
            f"{by_name['test_a_budgeted.py']['timeout_s']!r}"
        )
        assert by_name["test_b_unbudgeted.py"]["verdict"] == "TIMEOUT", (
            "L12: the override must be per-file, not global; the unnamed sibling still had 3s"
        )
        assert "per-file budgets" in proc.stderr and "test_a_budgeted.py=12s" in proc.stderr, (
            f"L12: the override map must be echoed at startup; stderr={proc.stderr[-200:]!r}"
        )

        bad = subprocess.run(
            [sys.executable, str(HARNESS), str(tmpdir), "--budget", "nonsense"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert bad.returncode == 2, (
            f"L12: a malformed --budget must be refused loudly (rc=2), got {bad.returncode}"
        )

        proc3, _ = _sweep(
            tmpdir,
            ["-t", "3", "--import-grace", "2", "--budget", f"{tmp}/test_absent.py=9", "-w", "1"],
        )
        assert "matched no discovered file" in proc3.stderr, (
            "L12: an override that matches nothing must be reported, not silently ignored; "
            f"stderr={proc3.stderr[-200:]!r}"
        )


def test_l13_timeout_reports_observed_collection():
    """L13 (SUITE-COLLECT-1, the row's own premise): a file that COLLECTS and then hangs inside a
    test is an execution overrun, not a collect-time hang. It must stay TIMEOUT and its record must
    carry the collection count pytest actually printed (2), because the all-zero counts the harness
    used to report on every kill are exactly what made `tests/test_xv6_boot_regression.py` and
    `tests/test_probe_stval.py` look like pre-collection hangs to the row's author.
    """
    collects_then_hangs = (
        "import time\n\n\ndef test_a_ok():\n    assert True\n\n\n"
        "def test_b_hangs():\n    time.sleep(30)\n"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "test_collects_then_hangs.py").write_text(collects_then_hangs)
        sink = tmp / "records.jsonl"

        proc, records = _sweep(tmpdir, ["-t", "6", "--import-grace", "3", "-w", "1"], sink)
        rec = records[0]

        assert rec["verdict"] == "TIMEOUT", (
            f"L13: a file that collected and then hung is an overrun, not a collect-hang; "
            f"got {rec['verdict']!r}"
        )
        assert rec["counts"]["collected"] == 2, (
            "L13: the record must report the collection count pytest printed before the kill; "
            f"got {rec['counts']!r} (all-zero counts on a kill is the old blindness)"
        )
        assert "execution overrun" in rec["last_line"], (
            f"L13: the last line must name the overrun; got {rec['last_line']!r}"
        )
        assert proc.returncode != 0, "L13: an overrun sweep must not look green"


# ---------------------------------------------------------------------------
# SUITE-BASE-2 — roadmap row systems/GLYPH_SELF_HOSTING_ROADMAP.md:360:
#   commit-anchored sweep records (--manifest) + attributed re-measure (--since).
# ---------------------------------------------------------------------------


def test_l14_manifest_is_commit_anchored():
    """L14 (SUITE-BASE-2): --manifest PATH writes one JSON object carrying head_sha,
    timestamp with timezone offset, file/collected counts, and full verdicts dict
    matching --sink records. When --manifest is absent, no manifest file is created.
    """
    from datetime import datetime

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "test_a_ok.py").write_text("def test_ok():\n    assert True\n")
        sink = tmp / "records.jsonl"
        manifest_path = tmp / "manifest.json"

        proc, records = _sweep(
            tmpdir,
            ["-t", "20", "-w", "1", "--manifest", str(manifest_path)],
            sink=sink,
        )
        assert proc.returncode == 0, f"L14: sweep failed (exit {proc.returncode}): {proc.stderr}"
        assert manifest_path.is_file(), "L14: manifest file was not created"

        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        assert isinstance(manifest, dict), "L14: manifest must be a JSON object"

        # Assert: head_sha equals `git -C <repo> rev-parse HEAD`
        git_proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        expected_sha = git_proc.stdout.strip()
        assert manifest["head_sha"] == expected_sha, (
            f"L14: head_sha mismatch: {manifest['head_sha']!r} != {expected_sha!r}"
        )

        # Assert: timestamp parses via datetime.fromisoformat and has a non-null utcoffset()
        dt = datetime.fromisoformat(manifest["timestamp"])
        assert dt.utcoffset() is not None, "L14: timestamp must have timezone offset"

        # Assert: files / collected / verdicts agree exactly with sink records
        assert manifest["files"] == len(records), (
            f"L14: files count mismatch: {manifest['files']} != {len(records)}"
        )
        total_coll = sum(r["counts"]["collected"] for r in records)
        assert manifest["collected"] == total_coll, (
            f"L14: collected mismatch: {manifest['collected']} != {total_coll}"
        )

        all_verdicts = [
            "PASS",
            "FAIL",
            "TIMEOUT",
            "COLLECT-HANG",
            "OOM",
            "CRASH",
            "ERROR",
            "SKIPPED",
        ]
        assert set(manifest["verdicts"].keys()) == set(all_verdicts), (
            f"L14: verdicts keys mismatch: {set(manifest['verdicts'].keys())}"
        )
        for v in all_verdicts:
            expected_v = sum(1 for r in records if r["verdict"] == v)
            assert manifest["verdicts"][v] == expected_v, (
                f"L14: verdict {v} count mismatch: {manifest['verdicts'][v]} != {expected_v}"
            )

        assert manifest["roots"] == [str(tmpdir)]
        assert manifest["workers"] == 1
        assert manifest["timeout_s"] == 20.0
        assert manifest["import_grace_s"] == 60.0
        assert manifest["python_bin"] == sys.executable

        # Inertness: run the same sweep with NO --manifest
        with tempfile.TemporaryDirectory() as tmpdir2:
            tmp2 = Path(tmpdir2)
            (tmp2 / "test_a_ok.py").write_text("def test_ok():\n    assert True\n")
            sink2 = tmp2 / "records2.jsonl"
            proc2, _ = _sweep(tmpdir2, ["-t", "20", "-w", "1"], sink=sink2)
            assert proc2.returncode == 0
            # Assert no manifest file appeared anywhere in the temp dir
            json_files = list(tmp2.glob("*.json"))
            assert len(json_files) == 0, (
                f"L14: inertness failed, found json files: {json_files}"
            )


def test_l15_remeasure_attribution():
    """L15 (SUITE-BASE-2): --since PATH compares current sweep against a previous manifest:
    (a) head_sha == HEAD -> attribution_required False;
    (b) head_sha == HEAD~1 and delta != 0 -> attribution_required True and attribution non-empty;
    (c) head_sha == non-existent and delta != 0 -> attribution_unexplained True, and non-zero exit on fail.
    """
    from datetime import datetime

    git_head = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    git_head_prev = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD~1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # (a) --since <manifest> where manifest's head_sha is git rev-parse HEAD -> attribution_required false
    with tempfile.TemporaryDirectory() as tmpdir_a:
        tmp_a = Path(tmpdir_a)
        (tmp_a / "test_a_ok.py").write_text("def test_ok():\n    assert True\n")
        manifest_prev_a = tmp_a / "manifest_prev.json"
        manifest_out_a = tmp_a / "manifest_out.json"

        prev_data_a = {
            "head_sha": git_head,
            "timestamp": datetime.now().astimezone().isoformat(),
            "files": 1,
            "collected": 1,
            "verdicts": {
                "PASS": 1,
                "FAIL": 0,
                "TIMEOUT": 0,
                "COLLECT-HANG": 0,
                "OOM": 0,
                "CRASH": 0,
                "ERROR": 0,
                "SKIPPED": 0,
            },
            "roots": [str(tmpdir_a)],
            "workers": 1,
            "timeout_s": 20.0,
            "import_grace_s": 60.0,
            "python_bin": sys.executable,
        }
        manifest_prev_a.write_text(json.dumps(prev_data_a), encoding="utf-8")

        proc_a, _ = _sweep(
            tmpdir_a,
            [
                "-t", "20", "-w", "1",
                "--manifest", str(manifest_out_a),
                "--since", str(manifest_prev_a),
            ],
        )
        assert proc_a.returncode == 0, f"L15(a) failed: {proc_a.stderr}"
        out_a = json.loads(manifest_out_a.read_text(encoding="utf-8"))
        assert "since" in out_a, "L15(a): manifest missing 'since' section"
        since_a = out_a["since"]
        assert since_a["head_sha"] == git_head
        assert since_a["files_delta"] == 0
        assert since_a["collected_delta"] == 0
        assert since_a["attribution_required"] is False
        assert since_a["attribution_unexplained"] is False

    # (b) a hand-written previous manifest whose head_sha is git rev-parse HEAD~1 and whose
    # collected is current - 1 -> attribution_required true and attribution non-empty
    with tempfile.TemporaryDirectory() as tmpdir_b:
        tmp_b = Path(tmpdir_b)
        (tmp_b / "test_b_ok.py").write_text("def test_ok():\n    assert True\n")
        manifest_prev_b = tmp_b / "manifest_prev.json"
        manifest_out_b = tmp_b / "manifest_out.json"

        # Current collected will be 1, so previous collected = 1 - 1 = 0
        prev_data_b = {
            "head_sha": git_head_prev,
            "timestamp": datetime.now().astimezone().isoformat(),
            "files": 1,
            "collected": 0,
            "verdicts": {
                "PASS": 0,
                "FAIL": 0,
                "TIMEOUT": 0,
                "COLLECT-HANG": 0,
                "OOM": 0,
                "CRASH": 0,
                "ERROR": 0,
                "SKIPPED": 0,
            },
            "roots": [str(tmpdir_b)],
            "workers": 1,
            "timeout_s": 20.0,
            "import_grace_s": 60.0,
            "python_bin": sys.executable,
        }
        manifest_prev_b.write_text(json.dumps(prev_data_b), encoding="utf-8")

        proc_b, _ = _sweep(
            tmpdir_b,
            [
                "-t", "20", "-w", "1",
                "--manifest", str(manifest_out_b),
                "--since", str(manifest_prev_b),
            ],
        )
        assert proc_b.returncode == 0, f"L15(b) failed: {proc_b.stderr}"
        out_b = json.loads(manifest_out_b.read_text(encoding="utf-8"))
        assert "since" in out_b, "L15(b): manifest missing 'since' section"
        since_b = out_b["since"]
        assert since_b["head_sha"] == git_head_prev
        assert since_b["collected_delta"] == 1
        assert since_b["attribution_required"] is True
        assert isinstance(since_b["attribution"], list)
        assert len(since_b["attribution"]) > 0, "L15(b): attribution must be non-empty"
        for item in since_b["attribution"]:
            assert "commit" in item and "subject" in item
        assert since_b["attribution_unexplained"] is False

    # (c) a previous manifest with head_sha set to a non-existent sha and a non-zero delta ->
    # attribution_unexplained true (the loud case), and the harness must still exit non-zero
    # on the verdict path if a file failed — attribution never masks verdicts.
    with tempfile.TemporaryDirectory() as tmpdir_c:
        tmp_c = Path(tmpdir_c)
        (tmp_c / "test_c_fail.py").write_text("def test_f():\n    assert False, 'intentional'\n")
        manifest_prev_c = tmp_c / "manifest_prev.json"
        manifest_out_c = tmp_c / "manifest_out.json"

        prev_data_c = {
            "head_sha": "00000000000000000000000000000000deadbeef",
            "timestamp": datetime.now().astimezone().isoformat(),
            "files": 1,
            "collected": 0,
            "verdicts": {
                "PASS": 0,
                "FAIL": 0,
                "TIMEOUT": 0,
                "COLLECT-HANG": 0,
                "OOM": 0,
                "CRASH": 0,
                "ERROR": 0,
                "SKIPPED": 0,
            },
            "roots": [str(tmpdir_c)],
            "workers": 1,
            "timeout_s": 20.0,
            "import_grace_s": 60.0,
            "python_bin": sys.executable,
        }
        manifest_prev_c.write_text(json.dumps(prev_data_c), encoding="utf-8")

        proc_c, _ = _sweep(
            tmpdir_c,
            [
                "-t", "20", "-w", "1",
                "--manifest", str(manifest_out_c),
                "--since", str(manifest_prev_c),
            ],
        )
        assert proc_c.returncode != 0, (
            "L15(c): the harness must still exit non-zero on the verdict path if a file failed"
        )
        out_c = json.loads(manifest_out_c.read_text(encoding="utf-8"))
        assert "since" in out_c, "L15(c): manifest missing 'since' section"
        since_c = out_c["since"]
        assert since_c["attribution_required"] is True
        assert len(since_c["attribution"]) == 0
        assert since_c["attribution_unexplained"] is True


def test_l16_head_is_captured_before_files_run():
    """L16 (SUITE-BASE-2, orchestrator correction): the record must name the revision the sweep
    RAN ON, not whichever revision existed when it finished. Measured motivation — the first
    canonical sweep that used --manifest (2026-09-13, 471.59 s) had a parallel-session commit
    land mid-run, and the record it wrote named THAT commit (`b8859ae`) even though no file was
    executed against it; the anchoring the row asks for was therefore not actually provided.

    Here the move is synthesized instead of waited for: a temp git repo supplies --repo-root,
    a 3 s test file keeps the sweep busy, and HEAD is advanced while it runs. Pre-fix, the
    manifest's head_sha equals the SECOND commit (read at write time) -> this leg goes RED.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        work = tmp / "work"
        repo.mkdir()
        work.mkdir()
        (work / "test_slow_ish.py").write_text(
            "import time\n\n\ndef test_a():\n    time.sleep(3)\n    assert True\n"
        )

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "l16",
            "GIT_AUTHOR_EMAIL": "l16@example.invalid",
            "GIT_COMMITTER_NAME": "l16",
            "GIT_COMMITTER_EMAIL": "l16@example.invalid",
        }

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(repo)] + list(args),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

        git("init", "-q")
        git("commit", "-q", "--allow-empty", "-m", "first")
        first = git("rev-parse", "HEAD").stdout.strip()

        manifest = tmp / "manifest.json"
        proc = subprocess.Popen(
            [
                sys.executable,
                str(HARNESS),
                str(work),
                "-t",
                "25",
                "-w",
                "1",
                "--repo-root",
                str(repo),
                "--manifest",
                str(manifest),
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(1.0)
        git("commit", "-q", "--allow-empty", "-m", "second")
        second = git("rev-parse", "HEAD").stdout.strip()
        stdout, stderr = proc.communicate(timeout=120)

        assert first != second, "L16: fixture failed to advance HEAD mid-sweep"
        assert proc.returncode == 0, f"L16: sweep failed (exit {proc.returncode}): {stderr}"
        m = json.loads(manifest.read_text(encoding="utf-8"))

        assert m["head_sha"] == first, (
            "L16: the record must be anchored to the revision captured BEFORE any file ran; "
            f"got {m['head_sha']!r}, expected the original {first!r} (the move to {second!r} "
            "happened during the sweep)"
        )
        assert m["head_sha_end"] == second, (
            f"L16: head_sha_end must observe the post-sweep revision; got {m['head_sha_end']!r}"
        )
        assert m["head_moved_during_sweep"] is True, (
            "L16: a sweep whose HEAD moved underneath it must say so rather than silently "
            "anchoring to the newer revision"
        )
