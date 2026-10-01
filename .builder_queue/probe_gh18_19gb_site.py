#!/usr/bin/env python3
"""DEFECT-22 next_step(a): name the ~1.9 GB allocation site inside
tests/test_gh18_syscall_abi.py.

Phase 1 (L1-L3): run the file's tests in-process, one VmHWM reading per
test (cumulative high-water mark; the test where HWM jumps >= 500 MB is
the transient's owner). RED if no test is named.
Phase 2 (L4): re-drive the named test's steps under tracemalloc and
report the top current-peak allocation traces. RED if no single trace
holds >= 300 MB.

Writes output/probe_gh18_19gb_site_<ts>.jsonl. No test file modified.
"""

import importlib
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
sys.path.insert(0, str(REPO))

OUT = REPO / "output"
OUT.mkdir(exist_ok=True)
ART = OUT / f"probe_gh18_19gb_site_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
recs = []


def rec(**kw):
    kw["ts"] = time.time()
    recs.append(kw)
    with open(ART, "a") as f:
        f.write(json.dumps(kw, default=str) + "\n")


def vmhwm_kb():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    return -1


def phase1_named_test():
    """L1: import the test module; L2: run every test_* callable with a
    fresh tmpdir like pytest's fixture would; L3: name the HWM jump."""
    mod = importlib.import_module("tests.test_gh18_syscall_abi")
    rec(phase="L1", imported="tests.test_gh18_syscall_abi",
        hwm_kb_start=vmhwm_kb())
    names = [n for n in dir(mod) if n.startswith("test_")]
    results = []
    for n in sorted(names):
        fn = getattr(mod, n)
        if not callable(fn):
            continue
        before = vmhwm_kb()
        t0 = time.time()
        status = "pass"
        try:
            with tempfile.TemporaryDirectory() as d:
                import inspect
                sig = inspect.signature(fn)
                if len(sig.parameters) == 0:
                    fn()
                else:
                    fn(Path(d))
        except Exception:
            status = "FAIL: " + traceback.format_exc(limit=1).strip().splitlines()[-1]
        dt = time.time() - t0
        after = vmhwm_kb()
        results.append({"test": n, "hwm_before_kb": before,
                        "hwm_after_kb": after, "delta_mb": (after - before) / 1024.0,
                        "secs": round(dt, 2), "status": status})
        rec(phase="L2", **results[-1])
    jumps = [r for r in results if r["delta_mb"] >= 500]
    for j in jumps:
        rec(phase="L3", verdict="HWM_JUMP", **j)
    ok = bool(jumps)
    rec(phase="L3", verdict="PASS" if ok else "RED",
        named=[j["test"] for j in jumps],
        note="RED means no single test shows a >=500 MB HWM jump")
    return [j["test"] for j in jumps], mod


def phase2_tracemalloc(named, mod):
    """L4: tracemalloc top traces while re-running the named test(s)."""
    import tracemalloc
    verdict = "RED"
    top_lines = []
    for n in named:
        fn = getattr(mod, n, None)
        if fn is None:
            continue
        tracemalloc.start(25)
        import inspect
        try:
            with tempfile.TemporaryDirectory() as d:
                sig = inspect.signature(fn)
                if len(sig.parameters) == 0:
                    fn()
                else:
                    fn(Path(d))
        except Exception:
            rec(phase="L4", test=n, error=traceback.format_exc(limit=1))
        snap = tracemalloc.take_snapshot()
        tracemalloc.stop()
        stats = snap.statistics("lineno")
        total = sum(s.size for s in stats)
        rec(phase="L4", test=n, tracemalloc_total_mb=total / 1048576.0,
            n_traces=len(stats))
        for s in stats[:8]:
            line = f"{s.traceback.format()[-1]} size={s.size/1048576.0:.1f}MB count={s.count}"
            top_lines.append(line)
            rec(phase="L4", test=n, top=line)
        big = [s for s in stats if s.size >= 300 * 1048576]
        if big:
            verdict = "PASS"
            for s in big:
                rec(phase="L4", verdict="SITE_NAMED", test=n,
                    site=s.traceback.format()[-1],
                    size_mb=s.size / 1048576.0, count=s.count)
    rec(phase="L4", verdict=verdict,
        note="PASS requires >=1 trace >=300MB; RED = allocation not in Python-tracked domain")
    return verdict


def main():
    named, mod = phase1_named_test()
    if named:
        phase2_tracemalloc(named, mod)
    else:
        rec(phase="L4", skipped=True, note="no named test from phase 1")
    rec(phase="done", artifact=str(ART))
    print(f"ARTIFACT {ART}")
    print(f"NAMED_TESTS {named}")


if __name__ == "__main__":
    main()
