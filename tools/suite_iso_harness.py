#!/usr/bin/env python3
"""SUITE-ISO-1: Per-file isolation harness with bounded verdicts.

Executes each discovered test file in its own subprocess under a strict
wall-clock timeout. Emits machine-readable records (path, verdict, duration,
rc, counts, last output line, budget).

Verdicts:
  PASS    - all tests passed (or file collected 0 tests, rc=0 or 5)
  FAIL    - at least one test failed (rc=1, failures > 0)
  CRASH   - process died from a crash signal (SIGSEGV / SIGABRT, rc < 0 or rc in 134, 139)
  TIMEOUT - collection happened, execution exceeded the file's wall-clock budget
  COLLECT-HANG - the file was killed after --import-grace seconds with NO pytest output at all,
            i.e. it hung BEFORE pytest collected anything (coll=0; SUITE-COLLECT-1). Distinct
            from TIMEOUT because the two need opposite fixes: move the import-time work into a
            fixture (this verdict) vs. raise the file's budget (TIMEOUT).
  ERROR   - pytest collection or execution error (rc in 2, 3, 4)
  OOM     - process was KILLED, not crashed (SIGKILL, i.e. the cgroup OOM killer, or a
            `Killed` marker in the child's own output). An OOM-killed file is NEVER
            counted as pass or fail — counts stay all-zero and the signal is named.
  SKIPPED - not launched, because the sweep stopped after the first OOM kill
            (SWEEP-OOM-ACCT-1 / RULING_worker_memory_containment.md §(c))
"""

from __future__ import annotations

import argparse
from datetime import datetime
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

# SUITE-COLLECT-1: a file may run this many seconds with NO pytest output at all before it is
# classified COLLECT-HANG and killed early. `pytest <file> -q` prints NOTHING until a test
# completes, which is why the execution path now runs at pytest's default verbosity: it emits
# `collected N item(s)` the moment collection finishes (measured: `pytest tests/test_supply_census.py -q`
# -> only the warning block, then `7 passed in 0.15s`; default verbosity -> `collected 7 items`
# BEFORE the first test runs). The predicate below is deliberately tight: only pytest's own
# collection/summary vocabulary counts as evidence, so a test that prints dots or `[100%]` cannot
# make the harness believe a pre-collection hang was a normal run.
DEFAULT_IMPORT_GRACE_S = 60.0

_COLLECT_EVIDENCE = re.compile(
    r"(collected \d+ items?"
    r"|\d+ tests? collected"
    r"|\d+ (?:passed|failed|error|errors|skipped|deselected|xfailed|xpassed)\b)",
    re.MULTILINE,
)

_COLLECT_COUNT = re.compile(r"collected (\d+) items?")


CLASS_VOCABULARY = (
    "BUDGET-RAISE",
    "CONTENTION-SENSITIVE",
    "RESTRUCTURE",
    "KNOWN-INPUT",
)

DEFAULT_CLASS_ARTIFACT = "systems/SUITE_TIMEOUT_CLASSES.json"


def load_timeout_classes(
    path: Union[str, Path] = DEFAULT_CLASS_ARTIFACT,
) -> Dict[str, Any]:
    """Load and validate the timeout classification artifact.

    Every entry must carry an accepted class from CLASS_VOCABULARY;
    unknown class tokens are rejected with ValueError.
    """
    p = Path(path)
    if not p.is_file():
        repo_root = Path(__file__).resolve().parent.parent
        cand = repo_root / path
        if cand.is_file():
            p = cand
    if not p.is_file():
        raise FileNotFoundError(f"Timeout classes artifact not found: {path}")

    data = json.loads(p.read_text())
    entries = data.get("entries", [])
    for entry in entries:
        c = entry.get("class")
        if c not in CLASS_VOCABULARY:
            raise ValueError(
                f"Unknown class token {c!r} in artifact for path {entry.get('path')}; "
                f"expected one of {CLASS_VOCABULARY}"
            )
    return data


def unclassified_timeouts(
    records: Sequence[Any],
    artifact: Any = DEFAULT_CLASS_ARTIFACT,
) -> list[str]:
    """Return sorted list of paths from TIMEOUT records that have no entry in artifact.

    Returns [] when all are classified. Unknown class tokens in artifact are reported
    as violations (ValueError).
    """
    if isinstance(artifact, (str, Path)):
        data = load_timeout_classes(artifact)
    elif isinstance(artifact, dict):
        data = artifact
    else:
        data = {"entries": list(artifact)}

    entries = data.get("entries", [])
    classified_paths: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict):
            c = entry.get("class")
            if c not in CLASS_VOCABULARY:
                raise ValueError(
                    f"Unknown class token {c!r} in artifact; expected one of {CLASS_VOCABULARY}"
                )
            if "path" in entry:
                classified_paths.add(entry["path"])

    unclassified: set[str] = set()
    for rec in records:
        verdict = rec["verdict"] if isinstance(rec, dict) else getattr(rec, "verdict", None)
        if verdict == "TIMEOUT":
            path = rec["path"] if isinstance(rec, dict) else getattr(rec, "path", None)
            if path and path not in classified_paths:
                unclassified.add(path)

    return sorted(list(unclassified))


def has_collect_evidence(text: str) -> bool:
    """True once the child's output shows pytest got past collection (SUITE-COLLECT-1)."""
    return bool(_COLLECT_EVIDENCE.search(text or ""))


def collect_count_from(text: str) -> int:
    """The number of tests pytest reported collecting, or 0 when it printed no such line.

    Used on the TIMEOUT path: before SUITE-COLLECT-1 the counts were hardcoded all-zero whenever
    the child was killed, which made an execution overrun look exactly like a pre-collection hang
    (that is how the roadmap row came to read `tests/test_xv6_boot_regression.py` as a
    collect-time hang when it in fact collects 2 tests and then hangs inside one of them).

    SUITE-HEAVY-1: also used for counts.observed_collected on all branches.
    """
    match = _COLLECT_COUNT.search(text or "")
    if match:
        return int(match.group(1))
    m_coll = re.search(r"(\d+)\s+tests?\s+collected", text or "")
    if m_coll:
        return int(m_coll.group(1))
    return 0


def _kill_group(proc: "subprocess.Popen") -> None:
    """SIGKILL the child's whole process group (it runs in its own session)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass

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

    `counts` dictionary keys (all ints, never None):
    - `collected`: authoritative junitxml count, falling back to observed on TIMEOUT
    - `passed`: number of passed tests
    - `failed`: number of failed tests
    - `observed_collected`: collection count printed by pytest to stdout (0 when not observed)
    - `skipped`: skipped count parsed from junitxml/summary (0 when unknown)
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
        failed_nodeids: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            path=path,
            verdict=verdict,
            duration_s=round(duration_s, 4),
            rc=rc,
            counts=counts,
            last_line=last_line,
            timeout_s=timeout_s,
            failed_nodeids=list(failed_nodeids) if failed_nodeids is not None else [],
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

    @property
    def failed_nodeids(self) -> List[str]:
        return self["failed_nodeids"]


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

    m_skip = re.search(r"(\d+)\s+skipped", stdout)
    if m_skip:
        skip_from_out = int(m_skip.group(1))
        if not parsed_xml or skip_from_out > skipped:
            skipped = skip_from_out

    observed_collected = collect_count_from(stdout)

    if collect_only:
        # In collect-only mode, success means tests were collected (or 0 collected with rc=0/5)
        if rc in (0, 5):
            verdict = "PASS"
        else:
            verdict = "ERROR" if rc in (2, 3, 4) else "FAIL"
        counts = {
            "collected": collected,
            "passed": 0,
            "failed": 0,
            "observed_collected": observed_collected,
            "skipped": 0,
        }
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
        "observed_collected": observed_collected,
        "skipped": skipped,
    }
    return verdict, counts


# SWEEP-OOM-ACCT-1: a child that dies by SIGKILL was KILLED, it did not "fail". SIGKILL is the
# signal the cgroup OOM killer uses (three CONSTRAINT_MEMCG events measured 2026-09-13), so it gets
# its own verdict token and its signal is named in the record. RULING_worker_memory_containment.md
# §(c): an OOM-killed file is NEVER counted as pass or fail.
_KILLED_OUTPUT_MARKER = re.compile(r"\bKilled\b")
_CRASH_RC = (128 + signal.SIGSEGV, 128 + signal.SIGABRT, 139, 134)


def _kill_signal(rc: Optional[int], stdout: str) -> Optional[str]:
    """Name the signal that KILLED the child, or ``None`` if this death was not a kill.

    SIGKILL is always a kill. A crash signal (SIGSEGV / SIGABRT) stays ``CRASH`` — that is a bug
    in the file, i.e. work to do — unless the child's own output carries a ``Killed`` marker
    (a killed descendant / a shell reporting a kill), which is the same "someone killed it" class.
    """
    if rc is None:
        return None
    if rc < 0:
        signum = -rc
    elif rc in (128 + signal.SIGSEGV, 128 + signal.SIGABRT, 139, 134):
        signum = rc - 128
    else:
        return None

    if signum == signal.SIGKILL:
        return "SIGKILL"
    if _KILLED_OUTPUT_MARKER.search(stdout or ""):
        try:
            return signal.Signals(signum).name
        except ValueError:  # pragma: no cover - defensive
            return f"signal {signum}"
    return None


def parse_failed_nodeids(
    stdout: str, xml_path: Optional[str] = None
) -> List[str]:
    """Parse failing test node IDs from pytest stdout short summary info (or junitxml).

    Matches lines like:
        FAILED path/to/file.py::test_name - AssertionError...
        ERROR path/to/file.py::test_name - Exception...

    Strips the file-path prefix before '::', caps at 20, preserving discovery order.
    """
    failed: List[str] = []
    if stdout:
        raw = re.findall(r"^(?:FAILED|ERROR) (.*?)(?: - |$)", stdout, re.MULTILINE)
        if not raw:
            raw = re.findall(r"^(?:FAILED|ERROR) (\S+)", stdout, re.MULTILINE)
        for m in raw:
            m = m.strip()
            if not m:
                continue
            node = m.split("::", 1)[1] if "::" in m else m
            if node not in failed:
                failed.append(node)
            if len(failed) >= 20:
                break

    if not failed and xml_path and os.path.isfile(xml_path) and os.path.getsize(xml_path) > 0:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            suite = root.find("testsuite") if root.tag == "testsuites" else root
            if suite is not None:
                for tc in suite.findall("testcase"):
                    if tc.find("failure") is not None or tc.find("error") is not None:
                        name = tc.attrib.get("name", "")
                        node = name.split("::", 1)[1] if "::" in name else name
                        if node and node not in failed:
                            failed.append(node)
                        if len(failed) >= 20:
                            break
        except Exception:
            pass

    return failed


def run_single_file(
    file_path: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    collect_only: bool = False,
    python_bin: str = sys.executable,
    repo_root: Optional[Union[str, Path]] = None,
    import_grace_s: float = DEFAULT_IMPORT_GRACE_S,
) -> TestRecord:
    """Run a single test file in its own subprocess with a wall-clock timeout.

    SUITE-COLLECT-1: output is read incrementally, so a file that produces NO pytest output
    within `import_grace_s` is killed early and recorded as COLLECT-HANG instead of being
    folded into TIMEOUT at the full budget. When `import_grace_s >= timeout_s` the behaviour
    is exactly the pre-existing wall-clock-only behaviour.
    """
    start = time.perf_counter()
    cwd = str(repo_root) if repo_root else None

    # Use a temporary XML file for junit reports if not in collect_only mode
    xml_fd, xml_path = tempfile.mkstemp(prefix="iso_junit_", suffix=".xml")
    os.close(xml_fd)

    # SUITE-COLLECT-1: the execution path runs at pytest's DEFAULT verbosity so the
    # `collected N item(s)` line is emitted the moment collection finishes — with `-q` the first
    # output arrives only when a test COMPLETES, so a file with one long test is indistinguishable
    # from a file that never collected (measured: `pytest <file> -q` prints nothing at all for
    # 2 s while a single test sleeps; default verbosity prints `collected 1 item` in ~0.4 s).
    # PYTHONUNBUFFERED keeps that line from sitting in the child's stdio buffer.
    cmd = [python_bin, "-m", "pytest", file_path]
    if collect_only:
        cmd.append("--collect-only")
        cmd.append("-q")
    else:
        cmd.extend(["--junitxml", xml_path, "-rf", "--tb=no"])

    child_env = dict(os.environ)
    child_env["PYTHONUNBUFFERED"] = "1"

    timed_out = False
    collect_hang = False
    stdout = ""
    rc: Optional[int] = None

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=child_env,
            preexec_fn=os.setsid,  # Run in a new process group
        )

        # Read the child's output as it is produced: the only way to tell "no collection yet"
        # from "collection happened, execution overran".
        chunks: List[str] = []

        def _reader() -> None:
            try:
                for line in proc.stdout:  # type: ignore[union-attr]
                    chunks.append(line)
            except (ValueError, OSError):  # pragma: no cover - stream torn down by the kill
                pass

        reader = threading.Thread(target=_reader, name="iso-harness-reader", daemon=True)
        reader.start()

        hard_deadline = start + timeout_s
        grace_deadline = start + import_grace_s
        killed_early = False
        while True:
            polled = proc.poll()
            if polled is not None:
                rc = polled
                break
            now = time.perf_counter()
            if (
                import_grace_s < timeout_s
                and now >= grace_deadline
                and not has_collect_evidence("".join(chunks))
            ):
                collect_hang = True
                killed_early = True
                _kill_group(proc)
                break
            if now >= hard_deadline:
                timed_out = True
                killed_early = True
                _kill_group(proc)
                break
            time.sleep(0.05)

        if killed_early:
            try:
                rc = proc.wait(timeout=2.0)
            except Exception:  # pragma: no cover - defensive
                rc = -signal.SIGKILL
        reader.join(timeout=2.0)
        stdout = "".join(chunks)
    except Exception as exc:
        stdout = f"Subprocess launch error: {exc}"
        rc = 2

    duration_s = time.perf_counter() - start

    # Extract last non-empty line
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    last_line = lines[-1] if lines else ""

    observed = collect_count_from(stdout)

    if collect_hang:
        verdict = "COLLECT-HANG"
        counts = {
            "collected": 0,
            "passed": 0,
            "failed": 0,
            "observed_collected": 0,
            "skipped": 0,
        }
        last_line = (
            f"COLLECT-HANG: no pytest output (collection never started) within "
            f"{import_grace_s:.1f}s import grace (file budget was {timeout_s:.1f}s)"
        )
    elif timed_out:
        verdict = "TIMEOUT"
        # SUITE-COLLECT-1: report what was actually observed before the kill. Hardcoding 0 here
        # made an execution overrun indistinguishable from a pre-collection hang.
        # SUITE-HEAVY-1: observed_collected = collect count pytest printed to stdout.
        # collected keeps its current meaning (authoritative junitxml count, falling back to
        # observed on observed-TIMEOUT).
        counts = {
            "collected": observed,
            "passed": 0,
            "failed": 0,
            "observed_collected": observed,
            "skipped": 0,
        }
        last_line = f"TIMEOUT: exceeded {timeout_s:.1f}s budget"
        if observed:
            last_line += f" after collection was observed ({observed} collected) - execution overrun"
    else:
        # A kill is not a failure: name the signal, count it as neither pass nor fail.
        killed_by = _kill_signal(rc, stdout)
        if killed_by is not None:
            verdict = "OOM"
            counts = {
                "collected": 0,
                "passed": 0,
                "failed": 0,
                "observed_collected": observed,
                "skipped": 0,
            }
            last_line = (
                f"OOM: child killed by {killed_by} (rc={rc}) - neither a pass nor a fail"
            )
        # Check signal crashes
        elif rc is not None and (rc < 0 or rc in _CRASH_RC):
            verdict = "CRASH"
            counts = {
                "collected": 0,
                "passed": 0,
                "failed": 1,
                "observed_collected": observed,
                "skipped": 0,
            }
        else:
            verdict, counts = _parse_counts_and_verdict(
                stdout=stdout,
                rc=rc if rc is not None else 1,
                xml_path=xml_path,
                collect_only=collect_only,
            )

    failed_nodeids: List[str] = []
    if verdict == "FAIL":
        failed_nodeids = parse_failed_nodeids(stdout, xml_path=xml_path)

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
        failed_nodeids=failed_nodeids,
    )


def _resolve_budget(
    file_path: str,
    budget_overrides: Optional[Dict[str, float]],
) -> Optional[float]:
    """Exact-path per-file budget lookup for SUITE-COLLECT-1's ``--budget PATH=SECONDS``."""
    if not budget_overrides:
        return None
    cands = {file_path, os.path.normpath(file_path), os.path.abspath(file_path)}
    for key, value in budget_overrides.items():
        if key in cands:
            return value
    return None


def run_suite_iso(
    targets: Sequence[Union[str, Path]],
    timeout_s: float = DEFAULT_TIMEOUT_S,
    collect_only: bool = False,
    workers: int = DEFAULT_WORKERS,
    repo_root: Optional[Union[str, Path]] = None,
    python_bin: str = sys.executable,
    on_record: Optional[Any] = None,
    import_grace_s: Optional[float] = None,
    budget_overrides: Optional[Dict[str, float]] = None,
) -> List[TestRecord]:
    """Discover and run test files under target paths, returning records.

    `import_grace_s` (SUITE-COLLECT-1) bounds how long a file may produce no pytest output
    before it is classified COLLECT-HANG; `budget_overrides` maps an exact file path to its own
    wall-clock budget, overriding `timeout_s` for that file only.
    """
    grace = DEFAULT_IMPORT_GRACE_S if import_grace_s is None else import_grace_s
    all_files: List[str] = []
    for tgt in targets:
        for f in discover_test_files(tgt, repo_root=repo_root):
            if f not in all_files:
                all_files.append(f)

    if not all_files:
        return []

    if budget_overrides:
        used = {
            k
            for k in budget_overrides
            if any(_resolve_budget(f, {k: 0.0}) is not None for f in all_files)
        }
        unused = sorted(set(budget_overrides) - used)
        if unused:
            print(
                "WARNING: --budget override(s) matched no discovered file: "
                + ", ".join(unused),
                file=sys.stderr,
            )

    records: List[TestRecord] = []
    stopped = threading.Event()
    stop_reason: List[str] = []

    def _worker(f: str) -> TestRecord:
        file_budget = _resolve_budget(f, budget_overrides)
        budget = timeout_s if file_budget is None else file_budget
        # SWEEP-OOM-ACCT-1 (ruling §(c) fail-fast branch): once a file has been OOM-killed, stop
        # launching. Un-launched files are recorded SKIPPED — never pass, never fail — so a
        # truncated sweep cannot be read as a long red or, worse, as green.
        if stopped.is_set():
            rec = TestRecord(
                path=f,
                verdict="SKIPPED",
                duration_s=0.0,
                rc=None,
                counts={
                    "collected": 0,
                    "passed": 0,
                    "failed": 0,
                    "observed_collected": 0,
                    "skipped": 0,
                },
                last_line=(
                    "SKIPPED: not launched - sweep stopped after an OOM kill"
                    + (f" of {stop_reason[0]}" if stop_reason else "")
                ),
                timeout_s=budget,
                failed_nodeids=[],
            )
            if on_record:
                on_record(rec)
            return rec

        rec = run_single_file(
            file_path=f,
            timeout_s=budget,
            collect_only=collect_only,
            python_bin=python_bin,
            repo_root=repo_root,
            import_grace_s=grace,
        )
        if rec.verdict == "OOM" and not stopped.is_set():
            stop_reason.append(rec.path)
            stopped.set()
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
    """Non-zero exit code iff any file is FAIL, CRASH, TIMEOUT, COLLECT-HANG, ERROR, OOM or SKIPPED.

    OOM and SKIPPED are not failures of the work — an OOM-killed file is never counted as pass or
    fail — but they do mean the sweep did not cover what it was asked to cover, and a truncated
    sweep must not look green (SWEEP-OOM-ACCT-1). COLLECT-HANG is in the same class for the same
    reason: the file contributed no collected tests at all (SUITE-COLLECT-1).
    """
    for r in records:
        if r.verdict in (
            "FAIL",
            "CRASH",
            "TIMEOUT",
            "COLLECT-HANG",
            "ERROR",
            "OOM",
            "SKIPPED",
        ):
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


def parse_budget_overrides(raw: Optional[Sequence[str]]) -> Dict[str, float]:
    """Parse SUITE-COLLECT-1 ``--budget PATH=SECONDS`` entries into an exact-path map.

    Each path is stored both as written and as an absolute path so a relative CLI spelling
    (`tests/test_x.py`) matches the discovered path regardless of how discovery spelled it.
    Malformed entries raise ValueError — the caller turns that into a loud argparse failure.
    """
    overrides: Dict[str, float] = {}
    for entry in raw or []:
        path, sep, value = str(entry).rpartition("=")
        if not sep or not path:
            raise ValueError(f"--budget needs PATH=SECONDS, got {entry!r}")
        try:
            seconds = float(value)
        except ValueError:
            raise ValueError(f"--budget SECONDS must be a number, got {value!r}")
        if seconds <= 0:
            raise ValueError(f"--budget SECONDS must be > 0, got {seconds!r}")
        overrides[path] = seconds
        overrides[os.path.abspath(path)] = seconds
        overrides[os.path.normpath(path)] = seconds
    return overrides


def _resolve_head_sha(repo_root: Optional[Union[str, Path]] = None) -> Optional[str]:
    """Resolve git rev-parse HEAD in repo_root or current working directory.
    Returns the commit SHA, or None if git is unavailable or fails (SUITE-BASE-2).
    """
    cmd = ["git"]
    if repo_root:
        cmd.extend(["-C", str(repo_root)])
    cmd.extend(["rev-parse", "HEAD"])
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            if sha:
                return sha
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return None


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
        "--import-grace",
        type=float,
        default=DEFAULT_IMPORT_GRACE_S,
        metavar="S",
        help=(
            "Seconds a file may produce NO pytest output before it is classified COLLECT-HANG "
            f"and killed early (default: {DEFAULT_IMPORT_GRACE_S}). Only applies when it is "
            "smaller than --timeout; otherwise the wall-clock budget governs (SUITE-COLLECT-1)"
        ),
    )
    parser.add_argument(
        "--budget",
        action="append",
        default=None,
        metavar="PATH=SECONDS",
        help=(
            "Per-file wall-clock budget override for an exact discovered file path; "
            "repeatable, e.g. --budget tests/test_xv6_boot_regression.py=300 (SUITE-COLLECT-1)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Root directory of the repository (default: current directory)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        metavar="PATH",
        help="Write sweep manifest JSON object to PATH when the sweep finishes (SUITE-BASE-2)",
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="PATH",
        help="Previous manifest to compute attribution against; requires --manifest (SUITE-BASE-2)",
    )

    args = parser.parse_args(argv)

    if args.since and not args.manifest:
        parser.error("--since requires --manifest")

    prev_manifest: Optional[Dict[str, Any]] = None
    if args.since:
        try:
            since_path = Path(args.since)
            prev_manifest = json.loads(since_path.read_text(encoding="utf-8"))
            if not isinstance(prev_manifest, dict):
                raise ValueError(f"Previous manifest at {args.since} is not a JSON object")
            for req_key in ("head_sha", "files", "collected"):
                if req_key not in prev_manifest:
                    raise ValueError(f"Previous manifest at {args.since} missing {req_key!r}")
        except Exception as exc:
            print(
                f"ERROR: failed to read or parse --since manifest from {args.since}: {exc}",
                file=sys.stderr,
            )
            return 2

    try:
        budget_overrides = parse_budget_overrides(args.budget)
    except ValueError as exc:
        parser.error(str(exc))

    # SUITE-BASE-2: capture the revision under test BEFORE any file runs. Resolving HEAD at
    # manifest-write time names the revision that happened to exist when the sweep ended —
    # measured 2026-09-13: a parallel session committed during a 471 s sweep and the record
    # named a commit the sweep never ran on. `head_sha_end` + `head_moved_during_sweep` keep
    # that observable instead of hiding it.
    sweep_head_sha = _resolve_head_sha(args.repo_root)

    start_all = time.perf_counter()

    def _print_record(rec: TestRecord) -> None:
        if not args.json:
            color = {
                "PASS": "\033[32m",
                "FAIL": "\033[31m",
                "CRASH": "\033[35m",
                "TIMEOUT": "\033[33m",
                "COLLECT-HANG": "\033[36m",
                "ERROR": "\033[31m",
                "OOM": "\033[91m",
                "SKIPPED": "\033[90m",
            }.get(rec.verdict, "")
            reset = "\033[0m"
            counts_str = (
                f"coll={rec.counts['collected']} pass={rec.counts['passed']} fail={rec.counts['failed']}"
            )
            extra = f" (failed: {', '.join(rec.failed_nodeids)})" if rec.failed_nodeids else ""
            print(
                f"[{color}{rec.verdict:<7}{reset}] {rec.path} "
                f"({rec.duration_s:.2f}s, rc={rec.rc}, {counts_str}) - {rec.last_line}{extra}"
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

    if budget_overrides:
        print(
            "per-file budgets: "
            + ", ".join(f"{k}={v:g}s" for k, v in sorted(budget_overrides.items())),
            file=sys.stderr,
        )
    print(
        f"import grace: {args.import_grace:g}s; sweep budget: {args.timeout:g}s",
        file=sys.stderr,
    )

    try:
        records = run_suite_iso(
            targets=args.targets,
            timeout_s=args.timeout,
            collect_only=args.collect_only,
            workers=args.workers,
            repo_root=args.repo_root,
            on_record=_dispatch,
            import_grace_s=args.import_grace,
            budget_overrides=budget_overrides,
        )
    finally:
        if sink_fd is not None:
            os.close(sink_fd)

    total_duration = time.perf_counter() - start_all
    total_collected = sum(r.counts["collected"] for r in records)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        verdict_counts: Dict[str, int] = {}
        for r in records:
            verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

        summary = ", ".join(f"{v}: {c}" for v, c in sorted(verdict_counts.items()))
        print("\n" + "=" * 70)
        print(
            f"Sweep finished in {total_duration:.2f}s. Files: {len(records)}, "
            f"Total collected: {total_collected}\nVerdicts: {summary or 'None'}"
        )
        print("=" * 70)

    manifest_write_failed = False
    if args.manifest:
        ALL_VERDICTS = (
            "PASS",
            "FAIL",
            "TIMEOUT",
            "COLLECT-HANG",
            "OOM",
            "CRASH",
            "ERROR",
            "SKIPPED",
        )
        manifest_verdicts = {v: 0 for v in ALL_VERDICTS}
        for r in records:
            manifest_verdicts[r.verdict] = manifest_verdicts.get(r.verdict, 0) + 1

        head_sha = sweep_head_sha  # captured BEFORE any file ran — the revision actually under test
        head_sha_end = _resolve_head_sha(args.repo_root)
        manifest_data: Dict[str, Any] = {
            "head_sha": head_sha,
            "head_sha_end": head_sha_end,
            "head_moved_during_sweep": bool(head_sha and head_sha_end and head_sha != head_sha_end),
            "timestamp": datetime.now().astimezone().isoformat(),
            "files": len(records),
            "collected": total_collected,
            "verdicts": manifest_verdicts,
            "roots": list(args.targets),
            "workers": int(args.workers),
            "timeout_s": float(args.timeout),
            "import_grace_s": float(args.import_grace),
            "python_bin": str(sys.executable),
        }

        if prev_manifest is not None:
            prev_head = prev_manifest.get("head_sha")
            prev_files = int(prev_manifest.get("files", 0))
            prev_collected = int(prev_manifest.get("collected", 0))

            files_delta = len(records) - prev_files
            collected_delta = total_collected - prev_collected
            attribution_required = bool(collected_delta != 0 or files_delta != 0)

            attribution: List[Dict[str, str]] = []
            if prev_head and head_sha and prev_head != head_sha:
                repo_root_path = (
                    Path(args.repo_root).resolve()
                    if args.repo_root
                    else Path.cwd().resolve()
                )
                valid_repo_roots: List[str] = []
                for tgt in args.targets:
                    tgt_p = Path(tgt)
                    if not tgt_p.is_absolute():
                        tgt_p = repo_root_path / tgt_p
                    try:
                        rel = tgt_p.resolve().relative_to(repo_root_path)
                        valid_repo_roots.append(str(rel))
                    except ValueError:
                        pass

                log_cmd = ["git"]
                if args.repo_root:
                    log_cmd.extend(["-C", str(args.repo_root)])
                log_cmd.extend(["log", "--format=%h %s", f"{prev_head}..{head_sha}"])
                if valid_repo_roots:
                    log_cmd.append("--")
                    log_cmd.extend(valid_repo_roots)

                try:
                    log_proc = subprocess.run(
                        log_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )
                    if log_proc.returncode == 0:
                        for line in log_proc.stdout.splitlines():
                            line = line.strip()
                            if line:
                                parts = line.split(" ", 1)
                                c_sha = parts[0]
                                c_subj = parts[1] if len(parts) > 1 else ""
                                attribution.append({"commit": c_sha, "subject": c_subj})
                except Exception:
                    pass

            attribution_unexplained = bool(attribution_required and len(attribution) == 0)

            manifest_data["since"] = {
                "head_sha": prev_head,
                "files_delta": files_delta,
                "collected_delta": collected_delta,
                "attribution_required": attribution_required,
                "attribution": attribution,
                "attribution_unexplained": attribution_unexplained,
            }

        try:
            m_path = Path(args.manifest)
            if m_path.parent and not m_path.parent.exists():
                m_path.parent.mkdir(parents=True, exist_ok=True)
            m_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"ERROR: failed to write manifest to {args.manifest}: {exc}", file=sys.stderr)
            manifest_write_failed = True

    exit_code = compute_exit_code(records)
    if manifest_write_failed:
        return 2 if exit_code == 0 else exit_code
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
