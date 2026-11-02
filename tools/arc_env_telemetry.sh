#!/usr/bin/env bash
# tools/arc_env_telemetry.sh — arc-run environment telemetry collector (DEFECT-22).
#
# Prints one JSON object, one line, on stdout, and exits 0.
# Keys:
#   cgroup                  the reader's own cgroup v2 path from /proc/self/cgroup
#   mem_limit_bytes         <cgroup>/memory.max (null when max)
#   mem_current_bytes       <cgroup>/memory.current
#   mem_peak_bytes          <cgroup>/memory.peak
#   mem_swap_max_bytes      <cgroup>/memory.swap.max (null when max)
#   oom_kill_total          oom_kill counter from <cgroup>/memory.events
#   loadavg                 /proc/loadavg first three fields
#   journal_oom_kill_window count of kernel Killed process lines since ISO timestamp in $1 (null when omitted)
#   at_utc                  date -u +%Y-%m-%dT%H:%M:%SZ
set -u

PY="${PY:-/usr/bin/python3}"
SINCE_ISO="${1:-}"

exec "$PY" - "$SINCE_ISO" <<'PYEOF'
import datetime
import json
import os
import subprocess
import sys

cgroup_path = None
try:
    with open("/proc/self/cgroup", "r") as f:
        for line in f:
            parts = line.strip().split("::", 1)
            if len(parts) == 2 and parts[0] == "0":
                cgroup_path = parts[1]
                break
            elif line.startswith("0:"):
                cgroup_path = line.strip().split(":", 2)[-1]
                break
    if cgroup_path is None:
        sys.stderr.write("WARNING: no cgroup v2 entry found in /proc/self/cgroup\n")
except Exception as e:
    sys.stderr.write(f"WARNING: failed to read /proc/self/cgroup: {e}\n")

cgroup_dir = None
if cgroup_path is not None:
    cgroup_dir = os.path.join("/sys/fs/cgroup", cgroup_path.lstrip("/"))
    if not os.path.isdir(cgroup_dir):
        sys.stderr.write(f"WARNING: cgroup directory {cgroup_dir} does not exist\n")
        cgroup_dir = None

def read_cgroup_file(filename):
    if not cgroup_dir:
        return None
    p = os.path.join(cgroup_dir, filename)
    try:
        with open(p, "r") as f:
            return f.read().strip()
    except Exception as e:
        sys.stderr.write(f"WARNING: failed to read {p}: {e}\n")
        return None

# mem_limit_bytes (<cgroup>/memory.max, null when max)
mem_limit_raw = read_cgroup_file("memory.max")
mem_limit_bytes = None
if mem_limit_raw is not None:
    if mem_limit_raw == "max":
        mem_limit_bytes = None
    else:
        try:
            mem_limit_bytes = int(mem_limit_raw)
        except Exception as e:
            sys.stderr.write(f"WARNING: invalid memory.max {mem_limit_raw!r}: {e}\n")

# mem_current_bytes (<cgroup>/memory.current)
mem_current_raw = read_cgroup_file("memory.current")
mem_current_bytes = None
if mem_current_raw is not None:
    try:
        mem_current_bytes = int(mem_current_raw)
    except Exception as e:
        sys.stderr.write(f"WARNING: invalid memory.current {mem_current_raw!r}: {e}\n")

# mem_peak_bytes (<cgroup>/memory.peak)
mem_peak_raw = read_cgroup_file("memory.peak")
mem_peak_bytes = None
if mem_peak_raw is not None:
    try:
        mem_peak_bytes = int(mem_peak_raw)
    except Exception as e:
        sys.stderr.write(f"WARNING: invalid memory.peak {mem_peak_raw!r}: {e}\n")

# mem_swap_max_bytes (<cgroup>/memory.swap.max, null when max)
mem_swap_raw = read_cgroup_file("memory.swap.max")
mem_swap_max_bytes = None
if mem_swap_raw is not None:
    if mem_swap_raw == "max":
        mem_swap_max_bytes = None
    else:
        try:
            mem_swap_max_bytes = int(mem_swap_raw)
        except Exception as e:
            sys.stderr.write(f"WARNING: invalid memory.swap.max {mem_swap_raw!r}: {e}\n")

# oom_kill_total (oom_kill counter from <cgroup>/memory.events)
events_raw = read_cgroup_file("memory.events")
oom_kill_total = None
if events_raw is not None:
    for line in events_raw.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0] == "oom_kill":
            try:
                oom_kill_total = int(parts[1])
            except Exception as e:
                sys.stderr.write(f"WARNING: invalid oom_kill value {parts[1]!r}: {e}\n")
            break
    if oom_kill_total is None:
        sys.stderr.write("WARNING: oom_kill counter not found in memory.events\n")

# loadavg (/proc/loadavg first three fields)
loadavg = None
try:
    with open("/proc/loadavg", "r") as f:
        fields = f.read().strip().split()
        if len(fields) >= 3:
            loadavg = " ".join(fields[:3])
except Exception as e:
    sys.stderr.write(f"WARNING: failed to read /proc/loadavg: {e}\n")

# journal_oom_kill_window: count of kernel Killed process lines since ISO timestamp in $1
since_iso = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
journal_oom_kill_window = None
if since_iso is not None:
    journal_cmd = os.environ.get("TELEMETRY_JOURNAL_CMD")
    try:
        if journal_cmd:
            res = subprocess.run(
                f'{journal_cmd} "{since_iso}"',
                shell=True, capture_output=True, text=True
            )
            raw_output = res.stdout
        else:
            res = subprocess.run(
                ["journalctl", "-k", "--since", since_iso],
                capture_output=True, text=True
            )
            raw_output = res.stdout
        count = 0
        for line in raw_output.splitlines():
            if "Killed process" in line:
                count += 1
        journal_oom_kill_window = count
    except Exception as e:
        sys.stderr.write(f"WARNING: failed to query journal oom kills: {e}\n")
        journal_oom_kill_window = None

at_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

result = {
    "cgroup": cgroup_path,
    "mem_limit_bytes": mem_limit_bytes,
    "mem_current_bytes": mem_current_bytes,
    "mem_peak_bytes": mem_peak_bytes,
    "mem_swap_max_bytes": mem_swap_max_bytes,
    "oom_kill_total": oom_kill_total,
    "loadavg": loadavg,
    "journal_oom_kill_window": journal_oom_kill_window,
    "at_utc": at_utc
}

print(json.dumps(result))
sys.exit(0)
PYEOF
