#!/usr/bin/env python3
"""Peak-RSS per test file over tools/ + systems/ — NAMES the memory hog(s).

Probe (non-blocking smoke lane), NOT a gate. It answers the one question left open by
`.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md`: the 2026-09-13 11:28 OOM killed a
sweep with a worst child at `anon-rss:3,470,616 kB`, and the ticket's own option 2 says "name the hog,
then decide narrowly" — but the hog was never named. This probe names it.

POLICY IS UNTOUCHED: no per-child cap, no exclusion list, no worker-default change. Those are the
design question held for Jericho; this file only measures.

Method: one child per file, using the SAME command shape as the harness
(`tools/suite_iso_harness.py:264`: `<python> -m pytest <file> -q`) and the harness's own discovery
function, so the file set is the harness's set. Each child is waited with `os.wait4()`, so
`ru_maxrss` is attributed to THAT child — `resource.getrusage(RUSAGE_CHILDREN)` cannot do this, it is
a monotonic max over every child ever reaped. Children run in their own session (`setsid`) and are
killed by process group on timeout.

Artifact form: append-only JSONL, one START record before each child and one END record after, each
flushed + fsynced. If the enclosing worker scope is OOM-killed mid-child, the last START with no END
still names the file that was running — the probe is self-attributing under the exact failure it
exists to explain.

LIMITS (stated, not implied):
  * `ru_maxrss` is the direct pytest child's peak. A test that spawns a heavy grandchild is
    under-counted (the OOM kills the direct child, which is what this measures).
  * Serial by construction (one child at a time), so these are per-file footprints, not the
    concurrent footprint of a `-w 12` sweep.
  * The enclosing scope matters: run in the BACKGROUND and the 4 GiB `OOMPolicy=kill` wrapper applies
    (measured: `.builder_queue/REPAIR_PENDING_worker_cgroup_memory_limit.md`); run FOREGROUND and it
    inherits the uncapped gateway scope. The JSONL says which one this run saw (`scope_max_bytes`).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.suite_iso_harness import discover_test_files  # noqa: E402  (single source of truth)


def scope_max_bytes() -> int | None:
    """The run's own cgroup memory.max, as an integer, or None when uncapped."""
    try:
        cg = Path("/proc/self/cgroup").read_text().strip().split(":")[-1]
        p = Path("/sys/fs/cgroup") / cg.lstrip("/") / "memory.max"
        txt = p.read_text().strip()
        return None if txt == "max" else int(txt)
    except Exception:
        return None


class Sink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fh = path.open("a", buffering=1)
        self.n = 0

    def write(self, record: dict) -> None:
        self.fh.write(json.dumps(record, sort_keys=True) + "\n")
        self.fh.flush()
        os.fsync(self.fh.fileno())
        self.n += 1


def run_one(file_path: str, python_bin: str, timeout: float) -> dict:
    cmd = [python_bin, "-m", "pytest", file_path, "-q"]
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    pgid = proc.pid
    deadline = t0 + timeout
    timed_out = False
    status = None
    rusage = None
    while True:
        try:
            pid, status, rusage = os.wait4(proc.pid, os.WNOHANG)
        except ChildProcessError:
            pid = None
            break
        if pid:
            break
        if time.time() > deadline:
            timed_out = True
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            pid, status, rusage = os.wait4(proc.pid, 0)
            break
        time.sleep(0.05)
    wall = time.time() - t0
    if status is None:
        rc = None
        peak_kb = None
    else:
        try:
            rc = os.waitstatus_to_exitcode(status)
        except Exception:
            rc = None
        peak_kb = getattr(rusage, "ru_maxrss", None) if rusage else None
    return {
        "file": file_path,
        "rc": rc,
        "peak_rss_kb": peak_kb,
        "peak_rss_mb": round(peak_kb / 1024.0, 1) if peak_kb else None,
        "wall_s": round(wall, 2),
        "verdict": "TIMEOUT" if timed_out else ("PASS" if rc == 0 else f"RC={rc}"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="*", default=["tools", "systems"])
    ap.add_argument("-t", "--timeout", type=float, default=20.0, help="per-file wall-clock seconds")
    ap.add_argument("-o", "--out", default=None, help="JSONL path (default: output/probe_peak_rss_<ts>.jsonl)")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = Path(args.out) if args.out else REPO_ROOT / "output" / f"probe_peak_rss_{ts}.jsonl"
    files: list[str] = []
    per_root = {}
    for root in args.roots:
        found = discover_test_files(root)
        per_root[root] = len(found)
        files.extend(found)

    sink = Sink(out)
    meta = {
        "kind": "META",
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roots": args.roots,
        "per_root_counts": per_root,
        "total_files": len(files),
        "timeout_s": args.timeout,
        "python": args.python,
        "scope_max_bytes": scope_max_bytes(),
        "pid": os.getpid(),
    }
    sink.write(meta)
    print(f"META {json.dumps(meta, sort_keys=True)}", flush=True)

    results = []
    for i, f in enumerate(files, 1):
        sink.write({"kind": "START", "file": f, "i": i, "of": len(files), "t": time.time()})
        r = run_one(f, args.python, args.timeout)
        r["kind"] = "END"
        r["i"] = i
        sink.write(r)
        results.append(r)
        flag = ""
        if (r["peak_rss_mb"] or 0) >= 1024:
            flag = "  <<< >=1 GiB"
        elif (r["peak_rss_mb"] or 0) >= 512:
            flag = "  <<< >=512 MiB"
        print(f"[{i:>3}/{len(files)}] {r['verdict']:<10} {r['peak_rss_mb']!s:>8} MB "
              f"{r['wall_s']:>6.2f}s  {f}{flag}", flush=True)

    ordered = sorted([r for r in results if r["peak_rss_mb"]], key=lambda r: -r["peak_rss_mb"])
    summary = {
        "kind": "SUMMARY",
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": len(results),
        "timeouts": sum(1 for r in results if r["verdict"] == "TIMEOUT"),
        "nonzero_rc": sum(1 for r in results if r["verdict"].startswith("RC=")),
        "peak_over_1gib": [r["file"] for r in ordered if r["peak_rss_mb"] >= 1024],
        "top10": [{"file": r["file"], "peak_rss_mb": r["peak_rss_mb"], "verdict": r["verdict"]} for r in ordered[:10]],
        "sink": str(out),
    }
    sink.write(summary)
    print("SUMMARY " + json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
