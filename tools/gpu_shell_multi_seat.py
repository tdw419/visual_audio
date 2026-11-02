#!/usr/bin/env python3
"""Multi-seat GPU Linux: N concurrent seats from one master snapshot.

The game-server claim, measured: a game server does not boot a world per
player; it snapshots once and streams seats. Here, N independent
gpu_shell_live.py processes restore the SAME machine-state snapshot and
execute different scripted command streams concurrently on one GPU.

Each seat is a full private machine (six buffers, its own RAM image), so
writes in one seat's /tmp are invisible to every other seat. This tool
launches the seats, waits for them, and verifies that isolation from the
captured serial logs:

  pass requires, for every seat i:
    - exit code 0
    - seat i's marker ("User i: <name>") appears in seat i's log
    - every OTHER seat's marker is absent from seat i's log

Usage:
  GPU_POWER=high python tools/gpu_shell_multi_seat.py \
      --kernel  /tmp/h12/alpine_shell.lnx.bin \
      --snapshot /tmp/h12/shell_prompt_snapshot.npz \
      --seats 2

Output: per-seat log files plus a JSON summary line (SEAT_SUMMARY: {...}).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SEAT_NAMES = ["Alice", "Bob", "Carol", "David"]


def build_command(args: argparse.Namespace, seat: int) -> list[str]:
    """One seat = one gpu_shell_live.py process with its own command stream."""
    name = SEAT_NAMES[seat % len(SEAT_NAMES)]
    # NOTE: the minimal initramfs has no /tmp; the writable root carries
    # note.txt, so seat files live at /seatN.txt.
    script = [
        f'echo "User {seat + 1}: {name}" > /seat{seat + 1}.txt',
        f"cat /seat{seat + 1}.txt",
        "ls /",
    ]
    return [
        sys.executable,
        str(Path(__file__).with_name("gpu_shell_live.py")),
        "--kernel", args.kernel,
        "--snapshot", args.snapshot,
        "--max-steps", str(args.max_steps),
        "--script", *script,
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kernel", required=True, help="shell LNX container path")
    ap.add_argument("--snapshot", required=True, help="master snapshot to restore")
    ap.add_argument("--seats", type=int, default=2, help="number of concurrent seats")
    ap.add_argument("--outdir", default="/tmp/h12_multiseat")
    ap.add_argument("--max-steps", type=int, default=250_000_000)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[multi-seat] launching {args.seats} seats from {args.snapshot}", flush=True)
    t0 = time.time()
    procs: list[tuple[int, str, subprocess.Popen, Path]] = []
    for seat in range(args.seats):
        name = SEAT_NAMES[seat % len(SEAT_NAMES)]
        log_path = outdir / f"seat{seat + 1}_{name.lower()}.log"
        log_fh = open(log_path, "w")
        proc = subprocess.Popen(
            build_command(args, seat),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        procs.append((seat, name, proc, log_path))
        print(f"[multi-seat] seat {seat + 1} ({name}) pid={proc.pid} log={log_path}",
              flush=True)

    results = []
    for seat, name, proc, log_path in procs:
        rc = proc.wait()
        results.append({
            "seat": seat + 1,
            "name": name,
            "pid": proc.pid,
            "exit_code": rc,
            "log": str(log_path),
        })
    wall = time.time() - t0

    # Isolation verification. CRITICAL: judge only *output* lines. The
    # serial log echoes every command we send (prefixed "[live] sending:"
    # and the terminal echo of the keystrokes), so a naive substring
    # search matches the echo, not the file content. Normalize CR and
    # require the marker as a standalone line.
    def output_lines(raw: str) -> list[str]:
        lines = raw.replace("\r", "").split("\n")
        return [ln.strip() for ln in lines
                if ln.strip() and not ln.startswith("[live]")
                and not ln.strip().startswith("echo")]

    all_ok = True
    for r in results:
        mine = f"User {r['seat']}: {r['name']}"
        others = [
            f"User {s + 1}: {SEAT_NAMES[s % len(SEAT_NAMES)]}"
            for s in range(args.seats) if s + 1 != r["seat"]
        ]
        lines = output_lines(Path(r["log"]).read_text(errors="replace"))
        r["saw_own_marker"] = mine in lines
        r["leaked_markers"] = [m for m in others if m in lines]
        r["ok"] = (
            r["exit_code"] == 0
            and r["saw_own_marker"]
            and not r["leaked_markers"]
        )
        all_ok = all_ok and r["ok"]

    summary = {
        "seats": args.seats,
        "snapshot": args.snapshot,
        "wall_seconds": round(wall, 1),
        "all_isolated": all_ok,
        "results": results,
    }
    print(f"SEAT_SUMMARY: {json.dumps(summary, indent=2)}")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[multi-seat] {'PASS' if all_ok else 'FAIL'} "
          f"({args.seats} seats, {wall:.1f}s wall)", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
