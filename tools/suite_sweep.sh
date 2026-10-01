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

parse_bytes() {
  local str="$1"
  str="${str#"${str%%[![:space:]]*}"}"
  str="${str%"${str##*[![:space:]]}"}"
  if [[ ! "$str" =~ ^([0-9]+)([kKmMgGtT]?)[iI]?[bB]?$ ]]; then
    return 1
  fi
  local num="${BASH_REMATCH[1]}"
  local unit="${BASH_REMATCH[2]}"
  num=$((10#$num))
  if [[ "$num" -le 0 ]]; then
    return 1
  fi
  case "${unit^^}" in
    "") echo "$num" ;;
    K) echo $(( num * 1024 )) ;;
    M) echo $(( num * 1024 * 1024 )) ;;
    G) echo $(( num * 1024 * 1024 * 1024 )) ;;
    T) echo $(( num * 1024 * 1024 * 1024 * 1024 )) ;;
    *) return 1 ;;
  esac
}

BUDGET=12G; WORKERS=4
while [[ $# -gt 0 ]]; do
  case "$1" in
    -b|--budget)
      [[ $# -lt 2 ]] && { echo "usage: suite_sweep.sh [-b 12G] [-w 4] <command...>" >&2; exit 2; }
      BUDGET="$2"; shift 2;;
    -w|--workers)
      [[ $# -lt 2 ]] && { echo "usage: suite_sweep.sh [-b 12G] [-w 4] <command...>" >&2; exit 2; }
      WORKERS="$2"; shift 2;;
    --) shift; break;;
    *) break;;
  esac
done
[[ $# -eq 0 ]] && { echo "usage: suite_sweep.sh [-b 12G] [-w 4] <command...>" >&2; exit 2; }

# R6 & R8: Parse budget size
BUDGET_BYTES=$(parse_bytes "$BUDGET" 2>/dev/null) || {
  echo "usage error: invalid -b/--budget '${BUDGET}': must be a positive size (e.g. 12G, 4096M)" >&2
  exit 2
}

# R4: Worker count cap (max 4)
if [[ ! "$WORKERS" =~ ^[0-9]+$ ]] || [[ "$WORKERS" -le 0 ]]; then
  echo "usage error: invalid -w/--workers '${WORKERS}': must be a positive integer <= 4" >&2
  exit 2
fi
if [[ "$WORKERS" -gt 4 ]]; then
  echo "ERROR: -w/--workers (${WORKERS}) exceeds maximum allowed (4)" >&2
  exit 2
fi

# R5: Minimum 1 GiB per child
if (( BUDGET_BYTES < WORKERS * 1073741824 )); then
  echo "ERROR: per-worker budget (${BUDGET} / ${WORKERS} workers) is less than 1 GiB minimum" >&2
  exit 2
fi

# R1: Preflight: what is the enclosing scope's cap? Refuse loudly if we cannot widen it.
ENCLOSING=$(cat /proc/self/cgroup 2>/dev/null | cut -d: -f3)
CAP_FILE="${SWEEP_CAP_FILE:-/sys/fs/cgroup${ENCLOSING}/memory.max}"
CAP=$(cat "$CAP_FILE" 2>/dev/null || echo max)
CAP="${CAP#"${CAP%%[![:space:]]*}"}"
CAP="${CAP%"${CAP##*[![:space:]]}"}"
[[ -z "$CAP" ]] && CAP="max"
echo "enclosing scope memory.max = ${CAP} (from ${CAP_FILE})" >&2

if systemd-run --user --scope -p MemoryMax=1G --quiet /bin/true 2>/dev/null; then
  echo "widening to MemoryMax=${BUDGET} MemoryHigh=${BUDGET} (workers=${WORKERS})" >&2
  exec systemd-run --user --scope -p "MemoryMax=${BUDGET}" -p "MemoryHigh=${BUDGET}" \
       --setenv=SWEEP_BUDGET="${BUDGET}" --setenv=SWEEP_WORKERS="${WORKERS}" \
       --quiet -- "$@"
else
  # R2: If widening unavailable and BUDGET > CAP, refuse loudly and exit 3
  if [[ "$CAP" != "max" ]]; then
    CAP_BYTES=$(parse_bytes "$CAP" 2>/dev/null || echo "")
    if [[ -n "$CAP_BYTES" && "$BUDGET_BYTES" -gt "$CAP_BYTES" ]]; then
      echo "REFUSAL: cannot widen scope (systemd-run unavailable) and requested budget ${BUDGET} exceeds enclosing scope cap ${CAP} from ${CAP_FILE} (workers=${WORKERS})" >&2
      exit 3
    fi
  fi
  # R3: Widening unavailable but BUDGET <= CAP -> proceed
  echo "WARN: systemd-run --user --scope unavailable — cannot widen; scope cap (${CAP}) applies." >&2
  export SWEEP_BUDGET="$BUDGET" SWEEP_WORKERS="$WORKERS"
  exec "$@"
fi
