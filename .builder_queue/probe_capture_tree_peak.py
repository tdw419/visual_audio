#!/usr/bin/env python3
"""Capture-path footprint attribution: is the arc's 91 % -of-cap peak the TREE or the TOOLING?

Direct follow-on to `.builder_queue/probe_lega_peak_timeline.py` (this same tick). That probe measured
leg A's PLAIN path in-process: the pytest process's own `VmHWM` peaks at **2684 MB (63 % of the 4 GiB
worker cap)**, and the peak is ONE jump of +1925 MB inside
`tests/test_gh18_syscall_abi.py::test_gh18_syscall_table_window_reserved` — i.e. file-local, with no
upward drift across the 52 files. The capture path, however, reports `mem_peak_bytes` 3.91-3.93 GB
(91 % of cap) in its own sidecar. That ~1.25 GB difference is the number the containment decision
(`REPAIR_PENDING_worker_cgroup_memory_limit.md`) currently has to treat as unexplained.

This probe runs `tools/arc_lega_capture.sh` (unmodified, fresh seed, its own sidecar) and samples BOTH:
  * the whole process TREE (comm + VmRSS + VmHWM per process) once a second, and
  * the enclosing cgroup's `memory.current` / `memory.peak` / `memory.max`,
so the scope peak can be split into: gdb | python3 | wrapper shells | everything else (page cache,
kernel, process RSS not in the tree).

RUN IT IN THE BACKGROUND (`terminal(background=true)`): the Hermes background wrapper is what creates
the 4 GiB `OOMPolicy=kill` worker scope that the reported 91 % figure refers to; foreground inherits the
uncapped gateway scope and the reading would not be comparable. Consequence accepted: if the capture
path really is ~365 MB from the cap, this probe can be OOM-killed — so the JSONL is flushed every
sample and the last record still names the peak reached before the kill.

POLICY UNTOUCHED: no cap changed, no file excluded, no worker default moved. Measurement only.
LIMITS (stated, not implied): 1 Hz sampling; `VmHWM` is per-process; gdb's own symbol-table reads are
counted only once they are resident; a single run = n=1 (one pytest-randomly order).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_kv(path: str | Path) -> dict[str, int]:
    """Parse `VmRSS:`-style /proc/<pid>/status entries.

    MEASURED bug this tick: the first version partitioned on ": ", but /proc status lines separate
    key and value with ":\\t", so every value was silently dropped and the probe reported a 0 MB tree
    while the enclosing scope read 3.70 GB. Regex on "key: <int> kB" instead.
    """
    out: dict[str, int] = {}
    try:
        txt = Path(path).read_text()
    except Exception:
        return out
    for m in re.finditer(r"^([A-Za-z_]+):\s+(\d+) kB$", txt, re.M):
        out[m.group(1)] = int(m.group(2))
    return out


def build_ppid_map() -> dict[int, int]:
    """pid -> ppid for every visible process.

    `/proc/<pid>/task/<pid>/children` is NOT usable here (measured this tick: it yielded an empty
    set for the capture pid on every sample, so the first version of this probe reported a 0 MB tree
    while the scope read 3.70 GB). /proc/<pid>/stat field 4 (ppid) is read directly instead, with the
    comm field stripped by splitting on the LAST ')' since a comm may contain spaces or parens.
    """
    m: dict[int, int] = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            rest = Path(f"/proc/{d}/stat").read_text().rsplit(")", 1)[1].split()
            m[int(d)] = int(rest[1])
        except Exception:
            continue
    return m


def tree(root_pid: int) -> list[int]:
    pmap = build_ppid_map()
    kids_of: dict[int, list[int]] = {}
    for pid, ppid in pmap.items():
        kids_of.setdefault(ppid, []).append(pid)
    pids, stack = [], [root_pid]
    while stack:
        p = stack.pop()
        for k in kids_of.get(p, []):
            pids.append(k)
            stack.append(k)
    return pids


def cg_of(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/cgroup").read_text().strip().split(":")[-1]
    except Exception:
        return None


def cg_reads(cgpath: str) -> dict:
    base = Path("/sys/fs/cgroup") / cgpath.lstrip("/")
    out: dict[str, object] = {"scope": cgpath}
    for name in ("memory.current", "memory.peak", "memory.max"):
        try:
            out[name] = int((base / name).read_text().strip())
        except Exception:
            out[name] = None
    return out


def main() -> int:
    seed = sys.argv[1] if len(sys.argv) > 1 else str(int(time.time()))
    out = ROOT / "output" / f"probe_capture_tree_peak_seed{seed}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    fh = out.open("w")

    def rec(rec: dict) -> None:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    env = dict(os.environ, SEED=seed)
    t0 = time.time()
    proc = subprocess.Popen(["bash", "tools/arc_lega_capture.sh"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    rec({"kind": "START", "seed": seed, "probe_pid": os.getpid(),
         "started_utc": datetime.now(timezone.utc).isoformat(), "capture_pid": proc.pid})

    peak_tree = 0
    sample = 0
    while proc.poll() is None:
        sample += 1
        t = round(time.time() - t0, 2)
        pids = tree(proc.pid)
        procs, total = [], 0
        for p in pids:
            vms = read_kv(f"/proc/{p}/status")
            try:
                comm = Path(f"/proc/{p}/comm").read_text().strip()
            except Exception:
                comm = "?"
            rss = vms.get("VmRSS", 0)
            total += rss
            if rss > 51200:  # only processes worth naming (>50 MB)
                procs.append({"pid": p, "comm": comm, "rss_kb": rss, "hwm_kb": vms.get("VmHWM")})
        peak_tree = max(peak_tree, total)
        rec({"kind": "SAMPLE", "t": t, "tree_rss_kb": total, "n_procs": len(pids),
             "procs": procs, "cgroup": cg_reads(cg_of(os.getpid()) or "/")})
        time.sleep(1.0)

    rc = proc.returncode
    el = round(time.time() - t0, 2)
    # the capture script's own sidecar carries the authoritative cgroup peak
    sidecar = ROOT / "output" / f"arc_lega_capture_seed{seed}_" 
    side = None
    for cand in sorted(ROOT.glob(f"output/arc_lega_capture_seed{seed}_*.json")):
        try:
            side = json.loads(cand.read_text())
            sidecar = cand
        except Exception:
            pass
    env_after = (side or {}).get("env_after", {}) if isinstance(side, dict) else {}
    rec({"kind": "END", "rc": rc, "elapsed_s": el, "samples": sample,
         "peak_tree_rss_kb": peak_tree, "sidecar": str(sidecar),
         "sidecar_mem_peak_bytes": env_after.get("mem_peak_bytes"),
         "sidecar_mem_limit_bytes": env_after.get("mem_limit_bytes"),
         "sidecar_oom_kill_delta": env_after.get("oom_kill_delta")})
    fh.close()

    print(f"seed={seed} rc={rc} elapsed={el}s samples={sample}")
    print(f"peak tree RSS (sum of all procs under the capture script) = {peak_tree/1024:.1f} MB")
    if env_after.get("mem_peak_bytes"):
        cgp = env_after["mem_peak_bytes"]
        print(f"scope memory.peak (sidecar, authoritative) = {cgp/1024/1024:.1f} MB "
              f"= {cgp/4294967296*100:.1f}% of 4 GiB, limit={env_after.get('mem_limit_bytes')}")
        print(f"residual (scope peak - peak tree sum) = {(cgp - peak_tree*1024)/1024/1024:.1f} MB "
              f"(page cache / kernel / untracked)")
    print(f"jsonl: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
