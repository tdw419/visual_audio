#!/bin/bash
# Reproduce leg-3 compare, printing what the substitution actually emits
cd "$(dirname "$0")"
set -u
MEDIUM=rung5_medium.raw
WR_OFF=68096
# run_gate5.sh builds this hex into a per-run temp now, so the path is an
# argument rather than a fixed /tmp name another run may own.
EXP=${1:?usage: run_gate5_persist_probe.sh <expected_marker.hex from a gate run>}
python3 -c "m=open('$MEDIUM','rb').read()[$WR_OFF:$WR_OFF+2048];print(m.hex())" | tr -d '\n' | od -c | tail -3
echo "--- byte count from the pipeline:"
python3 -c "m=open('$MEDIUM','rb').read()[$WR_OFF:$WR_OFF+2048];print(m.hex())" | tr -d '\n' | wc -c
echo "--- expected file byte count:"
wc -c < "$EXP"
