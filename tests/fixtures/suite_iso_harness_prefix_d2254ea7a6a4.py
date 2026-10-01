#!/usr/bin/env python3
"""SUITE-ISO-1: Per-file isolation harness with bounded verdicts.

Executes each discovered test file in its own subprocess under a strict
wall-clock timeout. Emits machine-readable records (path, verdict, duration,
rc, counts, last output line, budget).

Verdicts:
  PASS    - all tests passed (or file collected 0 tests, rc=0 or 5)
  FAIL    - at least one test failed (rc=1, failures > 0)
  CRASH   - process killed by signal (rc < 0 or rc in 134, 139, etc.)
  TIMEOUT - execution exceeded wall-clock timeout budget
  ERROR   - pytest collection or execution error (rc in 2, 3, 4)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_WORKERS = min(16, os.cpu_count() or 4)

# Directories excluded during discovery:
# - hidden directories (.*) e.g. .git, .venv, .pytest_cache
# - __pycache__, node_modules
# - disabled / tests/disabled (retired test modules whose subjects no longer exist)
EXCLUDE_DIR_NAMES = {
    "__pycache__",
    "node_modules",
    "disabled",
}


class TestRecord(dict):
    """Machine-readable record for a single test file's execution.
    Inherits from dict for JSON serialization and dict indexing,
    while providing attribute accessors.
    """

    def __init__(
        self,
        path: str,
        verdict: str,
        duration_s: float,
        rc: Optional[int],
        counts: Dict[str, int],
        last_line: str,
        timeout_s: float,
    ) -> None:
        super().__init__(
            path=path,
            verdict=verdict,
            duration_s=round(duration_s, 4),
            rc=rc,
            counts=counts,
            last_line=last_line,
            timeout_s=timeout_s,
        )

    @property
    def path(self) -> str:
        return self["path"]

    @property
    def verdict(self) -> str:
        return self["verdict"]

    @property
    def duration_s(self) -> float:
        return self["duration_s"]

    @property
    def rc(self) -> Optional[int]:
        return self["rc"]

    @property
    def counts(self) -> Dict[str, int]:
        return self["counts"]

    @property
    def last_line(self) -> str:
        return self["last_line"]

    @property
    def timeout_s(self) -> float:
        return self["timeout_s"]


def discover_test_files(
    target: Union[str, Path],
    repo_root: Optional[Union[str, Path]] = None,
) -> List[str]:
    """Discover test files under a given directory or return single file.

    Discovery rules:
    - If target is a file: return [str(target)]
    - If target is a directory:
      - Recurse matching test_*.py and *_test.py
      - Exclude dirs matching EXCLUDE_DIR_NAMES or starting with '.'
    """
    p = Path(target)
    if not p.is_absolute() and repo_root:
        p = Path(repo_root) / p

    if p.is_file():
        return [str(p)]

    if not p.is_dir():
        return []

    discovered: List[str] = []
    for dirpath, dirnames, filenames in os.walk(p):
        # In-place prune of excluded directories
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".") and d not in EXCLUDE_DIR_NAMES
        ]

        for f in filenames:
            if (f.startswith("test_") or f.endswith("_test.py")) and f.endswith(".py"):
                full_path = os.path.join(dirpath, f)
                discovered.append(full_path)

    discovered.sort()
    return discovered


def _parse_counts_and_verdict(
    stdout: str,
    rc: int,
    xml_path: Optional[str],
    collect_only: bool,
) -> tuple[str, Dict[str, int]]:
    """Determine verdict and test counts from junitxml and stdout."""
    collected = 0
    passed = 0
    failed = 0
    errors = 0
    skipped = 0

    parsed_xml = False
    if xml_path and os.path.isfile(xml_path) and os.path.getsize(xml_path) > 0:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            suite = root.find("testsuite") if root.tag == "testsuites" else root
            if suite is not None:
                tests = int(suite.attrib.get("tests", 0))
                failures = int(suite.attrib.get("failures", 0))
                errors = int(suite.attrib.get("errors", 0))
                skipped = int(suite.attrib.get("skipped", 0))

                # Check for collection failure in xml
                has_collection_error = any(
                    "collection failure" in (tc.find("error").attrib.get("message", "")
                    if tc.find("error") is not None else "")
                    for tc in suite.findall("testcase")
                )

                if has_collection_error or (errors > 0 and tests == 1 and failures == 0):
                    # Pytest records collection failure as testcase with error
                    collected = 0
                    passed = 0
                    failed = 0
                else:
                    collected = tests
                    failed = failures
                    passed = max(0, tests - failures - errors - skipped)
                parsed_xml = True
        except Exception:
            parsed_xml = False

    # Also parse stdout for corroboration or fallback
    m_coll = re.search(r"(\d+)\s+tests?\s+collected", stdout)
    if m_coll:
        coll_from_out = int(m_coll.group(1))
        if not parsed_xml or coll_from_out > collected:
            collected = coll_from_out

    m_pass = re.search(r"(\d+)\s+passed", stdout)
    if m_pass:
        passed = int(m_pass.group(1))

    m_fail = re.search(r"(\d+)\s+failed", stdout)
    if m_fail:
        failed = int(m_fail.group(1))

    m_err = re.search(r"(\d+)\s+errors?", stdout)
    if m_err:
        errors = int(m_err.group(1))

    if collect_only:
        # In collect-only mode, success means tests were collected (or 0 collected with rc=0/5)
        if rc in (0, 5):
            verdict = "PASS"
        else:
            verdict = "ERROR" if rc in (2, 3, 4) else "FAIL"
        counts = {"collected": collected, "passed": 0, "failed": 0}
        return verdict, counts

    # Execution mode verdict mapping
    if rc == 0:
        verdict = "PASS"
        if passed == 0 and collected > 0 and failed == 0:
            passed = collected
    elif rc == 5:
        # rc=5 is Pytest NO_TESTS_COLLECTED
        verdict = "PASS"
        collected = 0
        passed = 0
        failed = 0
    elif rc == 1:
        verdict = "FAIL"
        if failed == 0:
            failed = 1
        if collected == 0:
            collected = max(1, passed + failed)
    elif rc in (2, 3, 4):
        verdict = "ERROR"
    else:
        # Check signal crashes
        if rc < 0 or rc in (128 + 11, 128 + 6, 139, 134):
            verdict = "CRASH"
        else:
            verdict = "FAIL" if failed > 0 else "ERROR"

    counts = {
        "collected": collected,
        "passed": passed,
        "failed": failed,
    }
    return verdict, counts


def run_single_file(
    file_path: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    collect_only: bool = False,
    python_bin: str = sys.executable,
    repo_root: Optional[Union[str, Path]] = None,
) -> TestRecord:
    """Run a single test file in its own subprocess with a wall-clock timeout."""
    start = time.perf_counter()
    cwd = str(repo_root) if repo_root else None

    # Use a temporary XML file for junit reports if not in collect_only mode
    xml_fd, xml_path = tempfile.mkstemp(prefix="iso_junit_", suffix=".xml")
    os.close(xml_fd)

    cmd = [python_bin, "-m", "pytest", file_path, "-q"]
    if collect_only:
        cmd.append("--collect-only")
    else:
        cmd.extend(["--junitxml", xml_path])

    timed_out = False
    stdout = ""
    rc: Optional[int] = None

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,  # Run in a new process group
        )
        try:
            stdout, _ = proc.communicate(timeout=timeout_s)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill entire process group cleanly
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                stdout, _ = proc.communicate(timeout=2.0)
            except Exception:
                pass
            rc = -signal.SIGKILL
    except Exception as exc:
        stdout = f"Subprocess launch error: {exc}"
        rc = 2

    duration_s = time.perf_counter() - start

    # Extract last non-empty line
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    last_line = lines[-1] if lines else ""

    if timed_out:
        verdict = "TIMEOUT"
        counts = {"collected": 0, "passed": 0, "failed": 0}
        last_line = f"TIMEOUT: exceeded {timeout_s:.1f}s budget"
    else:
        # Check signal crashes
        if rc is not None and (rc < 0 or rc in (128 + 11, 128 + 6, 139, 134)):
            verdict = "CRASH"
            counts = {"collected": 0, "passed": 0, "failed": 1}
        else:
            verdict, counts = _parse_counts_and_verdict(
                stdout=stdout,
                rc=rc if rc is not None else 1,
                xml_path=xml_path,
                collect_only=collect_only,
            )

    # Clean up temp xml
    if os.path.exists(xml_path):
        try:
            os.remove(xml_path)
        except OSError:
            pass

    return TestRecord(
        path=file_path,
        verdict=verdict,
        duration_s=duration_s,
        rc=rc,
        counts=counts,
        last_line=last_line,
        timeout_s=timeout_s,
    )


def run_suite_iso(
    targets: Sequence[Union[str, Path]],
    timeout_s: float = DEFAULT_TIMEOUT_S,
    collect_only: bool = False,
    workers: int = DEFAULT_WORKERS,
    repo_root: Optional[Union[str, Path]] = None,
    python_bin: str = sys.executable,
    on_record: Optional[Any] = None,
) -> List[TestRecord]:
    """Discover and run test files under target paths, returning records."""
    all_files: List[str] = []
    for tgt in targets:
        for f in discover_test_files(tgt, repo_root=repo_root):
            if f not in all_files:
                all_files.append(f)

    if not all_files:
        return []

    records: List[TestRecord] = []

    def _worker(f: str) -> TestRecord:
        rec = run_single_file(
            file_path=f,
            timeout_s=timeout_s,
            collect_only=collect_only,
            python_bin=python_bin,
            repo_root=repo_root,
        )
        if on_record:
            on_record(rec)
        return rec

    if workers > 1 and len(all_files) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_worker, f) for f in all_files]
            for fut in as_completed(futures):
                records.append(fut.result())
    else:
        for f in all_files:
            records.append(_worker(f))

    # Maintain deterministic file order in returned list
    order_map = {f: i for i, f in enumerate(all_files)}
    records.sort(key=lambda r: order_map.get(r.path, 999999))
    return records


def compute_exit_code(records: Sequence[TestRecord]) -> int:
    """Non-zero exit code iff any file is FAIL, CRASH, TIMEOUT, or ERROR."""
    for r in records:
        if r.verdict in ("FAIL", "CRASH", "TIMEOUT", "ERROR"):
            return 1
    return 0


_SINK_LOCK = threading.Lock()


def write_record_to_sink(fd: int, rec: TestRecord) -> None:
    """Append ONE complete JSON line for `rec` to an already-open sink fd.

    SUITE-ISO-2: the whole line is issued in a single ``os.write`` under a lock and
    then fsynced, so (a) at any instant every line in the file parses as JSON and
    (b) a record already reported complete cannot be lost to a process kill. Power
    loss / machine crash is a different guarantee and is NOT claimed. Records reach
    ``on_record`` from worker threads, hence the lock.
    """
    line = json.dumps(dict(rec), sort_keys=True) + "\n"
    with _SINK_LOCK:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="SUITE-ISO-1: Per-file isolation harness with bounded verdicts."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["tests"],
        help="Target directories or files to run (default: tests)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-file wall-clock timeout in seconds (default: {DEFAULT_TIMEOUT_S})",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect tests from each file without executing test bodies",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of parallel subprocess workers (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON array of records",
    )
    parser.add_argument(
        "--sink",
        "--jsonl",
        dest="sink",
        default=None,
        metavar="PATH",
        help=(
            "Append one JSON line per completed record to PATH as the sweep runs, "
            "so a kill cannot lose a finished verdict (independent of --json)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Root directory of the repository (default: current directory)",
    )

    args = parser.parse_args(argv)

    start_all = time.perf_counter()

    def _print_record(rec: TestRecord) -> None:
        if not args.json:
            color = {
                "PASS": "\033[32m",
                "FAIL": "\033[31m",
                "CRASH": "\033[35m",
                "TIMEOUT": "\033[33m",
                "ERROR": "\033[31m",
            }.get(rec.verdict, "")
            reset = "\033[0m"
            counts_str = (
                f"coll={rec.counts['collected']} pass={rec.counts['passed']} fail={rec.counts['failed']}"
            )
            print(
                f"[{color}{rec.verdict:<7}{reset}] {rec.path} "
                f"({rec.duration_s:.2f}s, rc={rec.rc}, {counts_str}) - {rec.last_line}"
            )

    sink_fd: Optional[int] = None
    if args.sink:
        sink_fd = os.open(
            args.sink, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND, 0o644
        )

    def _dispatch(rec: TestRecord) -> None:
        _print_record(rec)
        if sink_fd is not None:
            write_record_to_sink(sink_fd, rec)

    try:
        records = run_suite_iso(
            targets=args.targets,
            timeout_s=args.timeout,
            collect_only=args.collect_only,
            workers=args.workers,
            repo_root=args.repo_root,
            on_record=_dispatch,
        )
    finally:
        if sink_fd is not None:
            os.close(sink_fd)

    total_duration = time.perf_counter() - start_all

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        verdict_counts: Dict[str, int] = {}
        for r in records:
            verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

        summary = ", ".join(f"{v}: {c}" for v, c in sorted(verdict_counts.items()))
        total_collected = sum(r.counts["collected"] for r in records)
        print("\n" + "=" * 70)
        print(
            f"Sweep finished in {total_duration:.2f}s. Files: {len(records)}, "
            f"Total collected: {total_collected}\nVerdicts: {summary or 'None'}"
        )
        print("=" * 70)

    return compute_exit_code(records)


if __name__ == "__main__":
    sys.exit(main())
