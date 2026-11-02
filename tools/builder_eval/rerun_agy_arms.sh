#!/usr/bin/env bash
# rerun_agy_arms.sh — re-run the two agy matrix arms that were invalidated by the
# wrapper syntax error (exit 127 at 11:10), now that the wrapper is fixed and the
# matrix is no longer running. Sequential; appends to results.jsonl.
set -uo pipefail
cd /home/jericho/projects/zion/projects/visual_audio || exit 1

CMD='REPO=$PWD bash ~/.hermes/scripts/agy_implement.sh -f {brief}'
for task in bk14_demo bk12_wgsl_tier; do
    echo "### $(date +%H:%M:%S)  task=$task  candidate=agy (re-run, wrapper fixed)"
    timeout 3000 /usr/bin/python3 tools/builder_eval/run_eval.py \
        --task "$task" --label agy --candidate-cmd "$CMD" 2>&1 | \
        grep -E "GATE=|candidate exit=|INVALID|recorded" | head -4
    echo
done
echo "### re-runs complete $(date +%H:%M:%S)"
