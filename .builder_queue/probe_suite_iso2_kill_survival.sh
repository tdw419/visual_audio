#!/usr/bin/env bash
# Kill-survival probe for the SUITE-ISO-2 row (orchestrator-side, out of tree).
# usage: kill_survival_probe.sh <out.json> <kill_after_s> [sink_path]
#   no sink  -> exercises the pre-fix / --json path (RED expectation: 0 bytes)
#   with sink-> exercises the incremental sink (GREEN expectation: >=1 record)
set -u
REPO=/home/jericho/projects/zion/projects/visual_audio
OUT=${1:-/tmp/red_json.json}
KILL_AFTER=${2:-30}
SINK=${3:-}
HARNESS=${HARNESS:-$REPO/tools/suite_iso_harness.py}

D=$(mktemp -d)
printf 'import time\ndef test_slow():\n    time.sleep(25)\n' > "$D/test_slow_a.py"
cp "$D/test_slow_a.py" "$D/test_slow_b.py"

SINK_ARG=""
if [ -n "$SINK" ]; then SINK_ARG="--sink $SINK"; rm -f "$SINK"; fi

python3 "$HARNESS" "$D" --json $SINK_ARG -t 60 -w 1 > "$OUT" 2>&1 &
HPID=$!
sleep "$KILL_AFTER"
kill -9 "$HPID" 2>/dev/null
pkill -9 -f "pytest $D" 2>/dev/null
sleep 1

echo "harness=$HARNESS"
echo "stdout_bytes=$(wc -c < "$OUT")"
echo "stdout_head=[$(head -c 160 "$OUT")]"
if [ -n "$SINK" ]; then
  if [ -f "$SINK" ]; then
    echo "sink_bytes=$(wc -c < "$SINK")"
    echo "sink_lines=$(grep -c . "$SINK" 2>/dev/null || echo 0)"
    echo "sink_ends_with_newline=$( [ -n "$(tail -c 1 "$SINK")" ] && echo no || echo yes )"
    python3 - "$SINK" <<'PY'
import json, sys
p = sys.argv[1]
raw = open(p, "rb").read()
lines = raw.split(b"\n")
complete = [l for l in lines[:-1]]
torn = lines[-1]
print(f"sink_parse_complete={len(complete)} torn_tail_bytes={len(torn)}")
for i, l in enumerate(complete):
    rec = json.loads(l.decode())
    print(f"  rec{i}: {rec['path'].split('/')[-1]} verdict={rec['verdict']} rc={rec['rc']} dur={rec['duration_s']:.1f}")
PY
  else
    echo "sink_bytes=0 (missing)"
  fi
fi
rm -rf "$D"
