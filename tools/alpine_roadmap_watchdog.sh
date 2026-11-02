#!/usr/bin/env bash
# Read-mostly watchdog for the Alpine-emulator roadmap loop.
#
# Scope, deliberately narrow to avoid racing the main /loop:
#   - Reads the heartbeat file the worker writes (tools/alpine_roadmap_worker.sh).
#   - If a "dispatched" heartbeat is older than STALL_SECONDS, the hermes
#     dispatch is presumed hung: kill it (and only it, by matching the
#     glm-4.7 hermes -z process for THIS project's cwd) and record that in
#     the status file.
#   - NEVER edits alpine_emulator_roadmap.yaml, NEVER marks a task done,
#     NEVER dispatches a new hermes task. Repairing a hang and deciding
#     what to do about the roadmap are different responsibilities -- this
#     script only does the former so it can't collide with the main loop
#     editing the same YAML file concurrently.
set -uo pipefail
cd "$(dirname "$0")/.."

HEARTBEAT=/tmp/alpine_roadmap_loop_heartbeat
STATUS=/tmp/alpine_roadmap_watchdog_status
STALL_SECONDS=1800   # 30 min with no heartbeat progress = presumed hung

now=$(date -u +%s)

if [ ! -f "$HEARTBEAT" ]; then
  echo "ts=$(date -u +%FT%TZ) result=no_heartbeat_file note=loop_never_ran_or_file_missing" | tee "$STATUS"
  exit 0
fi

hb_line=$(cat "$HEARTBEAT")
hb_ts=$(echo "$hb_line" | grep -oP 'ts=\K[^ ]+')
hb_status=$(echo "$hb_line" | grep -oP 'status=\K[^ ]+')
hb_pid=$(echo "$hb_line" | grep -oP 'pid=\K[^ ]+')
hb_task=$(echo "$hb_line" | grep -oP 'task=\K[^ ]+')

hb_epoch=$(date -u -d "$hb_ts" +%s 2>/dev/null || echo 0)
age=$(( now - hb_epoch ))

echo "Heartbeat: $hb_line"
echo "Age: ${age}s (stall threshold: ${STALL_SECONDS}s)"

if [ "$hb_status" = "dispatched" ] && [ "$age" -gt "$STALL_SECONDS" ]; then
  echo "=== STALL DETECTED: dispatched heartbeat is ${age}s old ==="
  worker_pid_alive="no"
  if [ -n "$hb_pid" ] && kill -0 "$hb_pid" 2>/dev/null; then
    worker_pid_alive="yes"
  fi
  echo "worker_pid=$hb_pid alive=$worker_pid_alive"

  killed_any="no"
  # Only kill hermes processes invoked from THIS repo's worker script, matched
  # by cwd via /proc, never a blanket pkill hermes (other sessions may use it).
  for pid in $(pgrep -f "hermes -z.*glm-4.7" 2>/dev/null || true); do
    link_target=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
    if [ "$link_target" = "$(pwd)" ]; then
      echo "Killing hung hermes pid=$pid (cwd matches this repo)"
      kill "$pid" 2>/dev/null || true
      killed_any="yes"
    fi
  done

  echo "ts=$(date -u +%FT%TZ) result=stall_repaired task=$hb_task killed_hermes=$killed_any worker_pid=$hb_pid worker_alive=$worker_pid_alive" | tee "$STATUS"
else
  echo "ts=$(date -u +%FT%TZ) result=healthy task=$hb_task status=$hb_status age_seconds=$age" | tee "$STATUS"
fi
