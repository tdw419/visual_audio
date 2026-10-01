#!/usr/bin/env bash
# Leg #42 of the DEFECT-22 capture series (builder cron af3e62239ce2).
# Worker-scope launch: MemoryMax=4G transient scope, pinned seed logged either way.
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
SEED="${1:-2026091414}"
UNIT="d22-leg43"
TAG="leg42_seed${SEED}_$(git rev-parse --short HEAD)"

systemd-run --user --scope -p MemoryMax=4G --unit="$UNIT" \
  env SEED="$SEED" OUTDIR="output" \
  bash tools/arc_lega_capture.sh > "output/d22_${TAG}_launch.log" 2>&1
RC=$?
echo "scope_rc=$RC seed=$SEED"
exit "$RC"
