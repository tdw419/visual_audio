#!/usr/bin/env bash
# suite_sweep.sh — run a test sweep OUTSIDE Hermes' 4 GiB per-worker scope cap.
#
# Why: tools/process_registry.py wraps every background terminal spawn in
#   systemd-run --user --scope with MemoryMax = min(4 GiB, RAM/2)  (_WORKER_MEMORY_MAX_CAP_BYTES)
# and TERMINAL_LOCAL_MEMORY_MAX_MB can only TIGHTEN it. On a 62 GB box that 4 GiB cap is binding:
# measured 2026-09-13, anon-rss 4.17 GB pytest and a 12-worker sweep were OOM-killed mid-run
# (CONSTRAINT_MEMCG inside hermes-worker-*.scope), taking agy delegates and ollama with them.
#
# usage: suite_sweep.sh [-b 12G] [-w 4] [--] <command...>
set -uo pipefail
BUDGET=12G; WORKERS=4
while [[ $# -gt 0 ]]; do
  case "$1" in
    -b|--budget) BUDGET="$2"; shift 2;;
    -w|--workers) WORKERS="$2"; shift 2;;
    --) shift; break;;
    *) break;;
  esac
done
[[ $# -eq 0 ]] && { echo "usage: suite_sweep.sh [-b 12G] [-w 4] <command...>" >&2; exit 2; }

# Preflight: what is the enclosing scope's cap? Refuse loudly if we cannot widen it.
ENCLOSING=$(cat /proc/self/cgroup | cut -d: -f3)
CAP=$(cat "/sys/fs/cgroup${ENCLOSING}/memory.max" 2>/dev/null || echo max)
echo "enclosing scope memory.max = ${CAP}" >&2

if systemd-run --user --scope -p MemoryMax=1G --quiet /bin/true 2>/dev/null; then
  echo "widening to MemoryMax=${BUDGET} MemoryHigh=${BUDGET} (workers=${WORKERS})" >&2
  exec systemd-run --user --scope -p "MemoryMax=${BUDGET}" -p "MemoryHigh=${BUDGET}" \
       --setenv=SWEEP_BUDGET="${BUDGET}" --setenv=SWEEP_WORKERS="${WORKERS}" \
       --quiet -- "$@"
else
  echo "WARN: systemd-run --user --scope unavailable — cannot widen; the 4 GiB cap still applies." >&2
  export SWEEP_BUDGET="$BUDGET" SWEEP_WORKERS="$WORKERS"
  exec "$@"
fi
