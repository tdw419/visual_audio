#!/usr/bin/env python3
"""BK-18: memory-bounded sharded suite runner.

Runs pytest ONE TEST FILE PER SUBPROCESS (fresh interpreter per file), so
per-shard memory is released to the OS before the next shard starts. A
single-process full run OOM-kills in this lane's cgroup at ~4.17 GB
(~51% of 2122 tests; kernel OOM lines 2026-09-22 22:00/22:08/22:36 —
.builder_queue/RESEARCH_suite_oom_ceiling.md). Sharding bounds cumulative
memory; the summary artifact makes "suite status" a runnable claim.

Usage:
    python3 tools/run_suite_sharded.py [file ...] [--out PATH] [--tests-dir DIR]

  - with explicit files: run exactly those
  - with --tests-dir and no files: every tests/*.py in sorted order

Summary artifact (.builder_queue/SUITE_RUN_<...>.md):
    - one line per shard: PASS/FAIL/KILLED, passed=/failed=/skipped counts,
      wall time
    - TOTAL line
    - FAILING: named failing tests (or NONE)
    - KILLED shards section
    - self-imported test modules: NONE (or names)   <- L4 contract line
    - per-shard self_rss_kb samples                 <- L4 flatness evidence

Exit code: 0 iff every shard finished green (no FAIL, no KILLED).

L4 contract: the runner NEVER imports test modules in its own process
(each shard is a `python -m pytest <file>` subprocess); the summary proves
this at runtime by scanning sys.modules for anything named test_* or
conftest, and samples its own RSS before/after each shard.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


def _self_rss_kb() -> int:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def _self_imported_test_modules() -> list[str]:
    return sorted(
        name
        for name in sys.modules
        if name == "conftest" or re.match(r"test_[A-Za-z0-9_]*$", name)
    )


def _run_shard(pytest_file: Path):
    """Run one test file in a fresh subprocess. Returns (kind, passed, failed, skipped, wall, tail)."""
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(pytest_file), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=None,
    )
    wall = time.monotonic() - t0
    out = proc.stdout[-4000:]
    if proc.returncode < 0:
        # signal-killed subprocess: rc = -signum (the BK-18 motivating failure)
        return ("KILLED", 0, 0, 0, wall, out)
    m_p = re.search(r"(\d+) passed", proc.stdout)
    m_f = re.search(r"(\d+) failed", proc.stdout)
    m_s = re.search(r"(\d+) skipped", proc.stdout)
    passed = int(m_p.group(1)) if m_p else 0
    failed = int(m_f.group(1)) if m_f else 0
    skipped = int(m_s.group(1)) if m_s else 0
    if proc.returncode != 0 and passed == 0 and failed == 0 and skipped == 0:
        # collection error etc — treat as failed with the tail for names
        return ("FAIL", 0, 1, 0, wall, out)
    kind = "FAIL" if (proc.returncode != 0 or failed > 0) else "PASS"
    return (kind, passed, failed, skipped, wall, out)


def _failing_names(file: Path) -> list[str]:
    """Second, cheap pass to capture failing test NAMES (pytest -q --tb=no does
    list FAILED lines in its short summary)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(file), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=None,
    )
    return re.findall(r"FAILED (\S+)", proc.stdout)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="test files to run as shards")
    ap.add_argument("--tests-dir", default=None,
                    help="default to every tests/*.py under this dir")
    ap.add_argument("--out", default=None, help="summary artifact path")
    args = ap.parse_args(argv)

    if args.files:
        # BK18-RESUME-PATHFIX: a bare filename that does not resolve as given
        # but exists under tests/ is resolved there. Without this, a resume
        # list without the tests/ prefix produced a full artifact of
        # "FAIL passed=0 failed=1" collection errors (measured 2026-09-23:
        # 35/35 shards 0.2s each, all phantom). Only fix unambiguous names;
        # anything still missing fails loudly with exit 2.
        resolved: list[Path] = []
        tests_root = Path(__file__).resolve().parent.parent / "tests"
        for f in args.files:
            p = Path(f)
            if not p.exists() and p.parent == Path(".") and (tests_root / p.name).exists():
                p = tests_root / p.name
            if not p.exists():
                print(f"shard file not found: {f}", file=sys.stderr)
                return 2
            resolved.append(p)
        files = resolved
    elif args.tests_dir:
        root = Path(args.tests_dir)
        files = sorted(root.glob("*.py"))
        files = [f for f in files if f.name.startswith("test_")]
    else:
        root = Path(__file__).resolve().parent.parent / "tests"
        files = sorted(f for f in root.glob("test_*.py"))
    if not files:
        print("no shards selected", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent
        / ".builder_queue"
        / f"SUITE_RUN_{time.strftime('%Y%m%dT%H%M%S')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# SUITE RUN — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"runner: tools/run_suite_sharded.py, shards={len(files)}")

    def _flush() -> None:
        """Rewrite the artifact after every shard — a runner that gets
        OOM-killed mid-suite still leaves the partial result on disk."""
        def _total_line() -> str:
            suffix = " (INCOMPLETE)" if done[0] < len(files) else ""
            return (
                f"TOTAL passed={total_passed[0]} failed={total_failed[0]} "
                f"skipped={total_skipped[0]} shards_done={done[0]}/{len(files)}"
                f"{suffix}"
            )

        text_now = "\n".join(
            lines
            + [
                _total_line(),
                "FAILING: " + (", ".join(failing) if failing else "NONE"),
                "KILLED: " + (", ".join(killed) if killed else "NONE"),
                "self-imported test modules: "
                + (", ".join(_self_imported_test_modules()) or "NONE"),
                "self_rss_kb per shard: "
                + " ".join(f"self_rss_kb={v}" for v in rss_samples),
            ]
        ) + "\n"
        out_path.write_text(text_now)

    # one-element lists so _flush sees mutations without nonlocal
    total_passed = [0]
    total_failed = [0]
    total_skipped = [0]
    done = [0]
    killed: list[str] = []
    failing: list[str] = []
    any_bad = False
    rss_samples: list[int] = []
    _flush()

    for f in files:
        rss_before = _self_rss_kb()
        kind, passed, failed, skipped, wall, _tail = _run_shard(f)
        rss_after = _self_rss_kb()
        rss_samples.append(rss_after)
        total_passed[0] += passed
        total_failed[0] += failed
        total_skipped[0] += skipped
        done[0] += 1
        if kind == "KILLED":
            killed.append(f.name)
            any_bad = True
            lines.append(
                f"{f.name}: KILLED (signal) wall={wall:.1f}s passed=0 failed=0 skipped=0"
            )
        else:
            if kind == "FAIL":
                any_bad = True
                failing.extend(_failing_names(f))
            lines.append(
                f"{f.name}: {kind} passed={passed} failed={failed} "
                f"skipped={skipped} wall={wall:.1f}s"
            )
        _flush()

    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(main())
