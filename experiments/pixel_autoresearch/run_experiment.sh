#!/usr/bin/env bash
# run_experiment.sh — score the current encoder.py, keep it as best if it
# beats best_encoder.py, else revert encoder.py to best_encoder.py.
#
# Mirrors autoresearch's "train for 5 min, keep if val_bpb improved, else
# discard" loop, but scored instantly instead of on a wall-clock budget
# since there's no GPU training step here.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f best_encoder.py ]; then
    cp encoder.py best_encoder.py
    echo 0.0 > best_score.txt
fi

SCORE_JSON=$(python3 metric.py)
SCORE=$(python3 -c "import json,sys; print(json.loads('''$SCORE_JSON''')['score'])")
BEST=$(cat best_score.txt)

echo "$SCORE_JSON"
echo "score=$SCORE best=$BEST"

IS_BETTER=$(python3 -c "print(1 if $SCORE > $BEST else 0)")

if [ "$IS_BETTER" = "1" ]; then
    cp encoder.py best_encoder.py
    echo "$SCORE" > best_score.txt
    echo "KEEP: new best ($SCORE > $BEST)"
    mkdir -p log
    ts=$(date +%s)
    cp encoder.py "log/encoder_${ts}_score_${SCORE}.py"
else
    cp best_encoder.py encoder.py
    echo "DISCARD: reverted to best ($SCORE <= $BEST)"
fi
