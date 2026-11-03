#!/usr/bin/env python3
"""Guest probe — the GPU Linux substrate as a factory verification oracle.

Restores the snapshot seat, executes probe commands INSIDE the guest, and
checks the guest's own answers against pinned ground truth:

  1. `cat /proc/uptime` twice — the second value must be strictly greater
     (proves the guest scheduler is advancing, not a frozen image).
  2. `sha256sum /note.txt` — the guest computes the hash; the host only
     compares it against a pinned constant (--expect-sha). Zero shared
     assumptions: host Python and guest busybox share no allocator,
     compiler, or libc.

Guardrails:
  - Refuses to run when GPU utilization is high (another compute job is
    live) unless --force. A parked idle session (0% util) is fine.
  - Scripted commands only; ~2 minutes per run (snapshot restore).
    Milestone gates only — never routine cron ticks.

Exit 0 only when every check passes. Usage:

  python tools/guest_probe.py \
      --kernel /tmp/h12/alpine_shell.lnx.bin \
      --snapshot /tmp/h12/shell_prompt_snapshot.npz \
      [--expect-sha <hex>] [--log /tmp/probe.json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PROBE_SCRIPTS = ["cat /proc/uptime", "cat /proc/uptime", "sha256sum /note.txt"]


def gpu_busy(threshold_pct: float = 5.0) -> bool:
    """True when the GPU is running a real compute job right now."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        utils = [float(x) for x in out.split() if x.strip().isdigit()]
        return any(u > threshold_pct for u in utils)
    except (subprocess.SubprocessError, ValueError):
        return False  # cannot know -> do not block


def gpu_shell_pids() -> list[str]:
    try:
        out = subprocess.run(["pgrep", "-af", "gpu_shell_live"],
                             capture_output=True, text=True, timeout=10).stdout
    except subprocess.SubprocessError:
        return []
    return [ln for ln in out.splitlines() if ln.strip()]


def parse_probe(serial_text: str) -> dict:
    """Extract uptime readings and the guest-computed sha from raw serial."""
    clean = serial_text.replace("\r", "")
    uptimes = []
    for m in re.finditer(r"^\s*([0-9]+\.[0-9]+)\s+[0-9]+\.[0-9]+\s*$",
                         clean, re.M):
        uptimes.append(float(m.group(1)))
    shas = re.findall(r"^\s*([0-9a-f]{64})\s+/note\.txt\s*$", clean, re.M)
    return {"uptimes": uptimes, "guest_sha": shas[-1] if shas else None}


def run_probe(kernel: str, snapshot: str, max_steps: int,
              log_dir: Path) -> tuple[str, dict]:
    log_dir.mkdir(parents=True, exist_ok=True)
    serial_path = log_dir / "guest_probe_serial.log"
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable,
         str(Path(__file__).with_name("gpu_shell_live.py")),
         "--kernel", kernel, "--snapshot", snapshot,
         "--max-steps", str(max_steps), "--script", *PROBE_SCRIPTS],
        capture_output=True, text=True, timeout=max_steps // 10000,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    wall = time.time() - t0
    serial_text = proc.stdout + proc.stderr
    serial_path.write_text(serial_text, errors="replace")
    parsed = parse_probe(serial_text)
    parsed["exit_code"] = proc.returncode
    parsed["wall_seconds"] = round(wall, 1)
    return serial_text, parsed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--expect-sha", default=None,
                    help="pinned ground truth for /note.txt (64 hex)")
    ap.add_argument("--max-steps", type=int, default=250_000_000)
    ap.add_argument("--log-dir", default="/tmp/guest_probe")
    ap.add_argument("--force", action="store_true",
                    help="run even when GPU utilization is high")
    args = ap.parse_args()

    busy = gpu_busy()
    pids = gpu_shell_pids()
    if busy and not args.force:
        print("[probe] REFUSING: GPU utilization is high (live compute job). "
              "Re-run with --force only if that job is yours.", file=sys.stderr)
        return 2
    if pids:
        print(f"[probe] note: {len(pids)} existing gpu_shell_live process(es) "
              f"(idle park is fine): {pids}", file=sys.stderr)

    serial_text, parsed = run_probe(args.kernel, args.snapshot,
                                    args.max_steps, Path(args.log_dir))
    checks = {}
    checks["guest_exit_ok"] = parsed["exit_code"] == 0
    uptimes = parsed["uptimes"]
    checks["uptime_read_twice"] = len(uptimes) >= 2
    checks["guest_time_advances"] = (len(uptimes) >= 2
                                     and uptimes[-1] > uptimes[0])
    guest_sha = parsed["guest_sha"]
    checks["guest_computed_sha"] = guest_sha is not None
    if args.expect_sha:
        checks["sha_matches_ground_truth"] = (
            guest_sha is not None
            and guest_sha.lower() == args.expect_sha.lower()
        )

    ok = parsed["exit_code"] == 0 and all(checks.values())
    summary = {
        "probe": "guest_probe",
        "ok": ok,
        "checks": checks,
        "uptimes": uptimes,
        "guest_sha": guest_sha,
        "expected_sha": args.expect_sha,
        "wall_seconds": parsed["wall_seconds"],
        "serial_log": str(Path(args.log_dir) / "guest_probe_serial.log"),
    }
    print(f"GUEST_PROBE_SUMMARY: {json.dumps(summary, indent=2)}")
    (Path(args.log_dir) / "summary.json").write_text(
        json.dumps(summary, indent=2))
    if guest_sha and not args.expect_sha:
        # First run: emit the pin for the next run's --expect-sha.
        print(f"[probe] pin this as --expect-sha on future runs: {guest_sha}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
