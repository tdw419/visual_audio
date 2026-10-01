#!/usr/bin/env bash
# Run DEFECT-22 capture-series leg #74 (orchestrator cron af3e62239ce2, 2026-09-14).
# Worker-scope launch for mem telemetry comparability (see ledger scope_cap_measured).
set -u
cd /home/jericho/projects/zion/projects/visual_audio
SEED=$(python3 -c 'import random; print(random.getrandbits(32))')
HEAD=$(git rev-parse --short HEAD)
UNIT="d22-leg74"
echo "leg74 seed=$SEED head=$HEAD unit=$UNIT" | tee output/d22_leg74_launch.txt
exec systemd-run --user --scope -p MemoryMax=4G --unit="$UNIT" \
    env SEED="$SEED" bash tools/arc_lega_capture.sh
