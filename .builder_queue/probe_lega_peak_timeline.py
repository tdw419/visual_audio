#!/usr/bin/env python3
"""Leg-A peak-SHAPE probe: WHICH file owns the arc's 3.93 GB in-run peak?

Question this answers (named, not invented): `REPAIR_PENDING_worker_cgroup_memory_limit.md` and
`REPAIR_PENDING_suite_iso2_memory_containment.md` both rest on an arithmetic ask to Jericho —
a canonical arc leg A run drives its own worker cgroup to 2.97-3.93 GB against a 4 GiB hard cap
(91.5 % in the heavier sample), while the largest ISOLATED per-file peak over leg A's 52-file list
is 2.65 GB (`systems/RECEIPT_DEFECT22_LEGA_PER_FILE_RSS.md`). The ~1.28 GB gap between those two
numbers was stated as *unexplained* and its candidates were listed but not measured. This probe
measures the shape of the in-run peak: one pytest process, 52 files, sampling `VmHWM`/`VmRSS` from
/proc once a second, with each pytest `-v` progress line timestamped as it arrives.

What the answer decides (input only — no policy is applied here):
  * peak jumps at one file and is flat elsewhere  -> the peak is FILE-local; a per-file containment
    lever (exclusion or a per-child cap sized above that file) is sufficient.
  * peak drifts upward across many files         -> the peak is ACCUMULATION; a per-file cap cannot
    bound it, and only a per-worker bound or a smaller file set helps.

POLICY UNTOUCHED: no cap, no exclusion, no worker-default change, no engine/test edit. This is a
measurement in the probe (non-blocking) lane per `skeleton-driven-development`.

Run FOREGROUND on purpose: a background worker command gets a 4 GiB `OOMPolicy=kill` scope and the
measurement would then be taken against the very cap under study. The artifact records which scope
this run actually saw (`scope_max_bytes`), read from /proc/self/cgroup.

LIMITS (stated, not implied):
  * `VmHWM` is the pytest child's own peak (that is exactly the quantity the worker cap limits);
    descendants are sampled separately and summed, but a grandchild that dies before a sample is
    under-counted.
  * 1 Hz sampling: the jump time is resolved to ~1 s, and a test shorter than that can be missed.
  * Correlation is by wall-clock arrival of pytest's `-v` lines; if pytest buffered them, the
    per-line deltas would collapse to ~0 and the probe says so (`line_timing_ok`).
  * One seed = one order (pytest-randomly). The shape may be order-dependent; this is n=1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS_RE = re.compile(r"^(VmRSS|VmHWM|VmSize):\s+(\d+) kB", re.M)


def scope_max_bytes() -> int | None:
    try:
        cg = Path("/proc/self/cgroup").read_text().strip().split(":")[-1]
        p = Path("/sys/fs/cgroup") / cg.lstrip("/") / "memory.max"
        txt = p.read_text().strip()
        return None if txt == "max" else int(txt)
    except Exception:
        return None


def vms(pid: int) -> tuple[int | None, int | None]:
    try:
        txt = Path(f"/proc/{pid}/status").read_text()
    except Exception:
        return None, None
    vals = {k: int(v) for k, v in STATUS_RE.findall(txt)}
    return vals.get("VmRSS"), vals.get("VmHWM")


def descendants(pid: int) -> list[int]:
    out, stack = [], [pid]
    while stack:
        p = stack.pop()
        try:
            kids = Path(f"/proc/{p}/task/{p}/children").read_text().split()
        except Exception:
            kids = []
        for k in kids:
            out.append(int(k))
            stack.append(int(k))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=str(int(time.time())))
    ap.add_argument("--python", default="/usr/bin/python3")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    files = subprocess.run(
        "ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py "
        "| grep -vE 'glass_box|gh24_s2_mcp'",
        shell=True, cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    if not files:
        print("FATAL: no files matched the leg-A selector")
        return 2

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    out_json = Path(args.out or ROOT / "output" / f"probe_lega_peak_timeline_{args.seed}_{head}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)

    cmd = [args.python, "-u", "-m", "pytest", *files, "-v", "--tb=line",
           "-m", "not live_smoke", "-p", "randomly", f"--randomly-seed={args.seed}"]
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            start_new_session=True)
    lines: list[tuple[float, str]] = []
    lock = threading.Lock()

    def reader() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            with lock:
                lines.append((time.time() - t0, raw.rstrip("\n")))

    th = threading.Thread(target=reader, daemon=True)
    th.start()

    samples: list[dict] = []
    prev_hwm = 0
    while proc.poll() is None:
        rss, hwm = vms(proc.pid)
        kids = descendants(proc.pid)
        kid_rss = 0
        for k in kids:
            kr, _ = vms(k)
            kid_rss += kr or 0
        if hwm is not None:
            samples.append({
                "t": round(time.time() - t0, 2),
                "vm_rss_kb": rss, "vm_hwm_kb": hwm,
                "n_descendants": len(kids), "desc_rss_kb": kid_rss,
                "hwm_jump_kb": hwm - prev_hwm,
            })
            prev_hwm = hwm
        time.sleep(args.interval)
    th.join(timeout=5)
    rc = proc.returncode
    elapsed = round(time.time() - t0, 2)

    # --- analysis -----------------------------------------------------------
    peak = max(samples, key=lambda s: s["vm_hwm_kb"]) if samples else None
    line_span = (lines[-1][0] - lines[0][0]) if len(lines) > 1 else 0.0
    timing_ok = bool(lines) and line_span > 0.5 * elapsed > 0

    def test_at(t: float) -> str:
        last = "?"
        for lt, txt in lines:
            if lt <= t:
                last = txt
            else:
                break
        return last

    jumps = [s for s in samples if s["hwm_jump_kb"] >= 204800]  # >= 200 MB steps
    report = {
        "head": head, "seed": args.seed, "rc": rc, "elapsed_s": elapsed,
        "n_files": len(files), "n_samples": len(samples),
        "scope_max_bytes": scope_max_bytes(),
        "hwm_final_mb": round((peak or {}).get("vm_hwm_kb", 0) / 1024, 1),
        "hwm_final_pct_of_4gib": round((peak or {}).get("vm_hwm_kb", 0) / 1024 * 1024 / 4294967296 * 100, 1),
        "line_timing_ok": timing_ok, "line_span_s": round(line_span, 2),
        "big_jumps": [
            {"t": s["t"], "delta_mb": round(s["hwm_jump_kb"] / 1024, 1),
             "hwm_mb": round(s["vm_hwm_kb"] / 1024, 1), "during": test_at(s["t"])}
            for s in jumps
        ],
        "samples": samples,
        "lines": [{"t": round(t, 2), "line": l} for t, l in lines],
    }
    out_json.write_text(json.dumps(report, indent=1))

    print(f"HEAD={head} SEED={args.seed} rc={rc} elapsed={elapsed}s files={len(files)} "
          f"samples={len(samples)} scope_max={report['scope_max_bytes']}")
    print(f"line_timing_ok={timing_ok} line_span={round(line_span,2)}s (probe stdout lines={len(lines)})")
    print(f"VmHWM final = {report['hwm_final_mb']} MB = {report['hwm_final_pct_of_4gib']}% of 4 GiB")
    print(f"big jumps (>=200 MB): {len(jumps)}")
    for j in report["big_jumps"]:
        print(f"  t={j['t']:>7.2f}s  +{j['delta_mb']:>8.1f} MB -> {j['hwm_mb']:>8.1f} MB   during: {j['during'][:100]}")
    print(f"artifact: {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
