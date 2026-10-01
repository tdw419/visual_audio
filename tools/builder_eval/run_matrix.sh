#!/usr/bin/env bash
# run_matrix.sh — execute the builder benchmark matrix and append to results.jsonl.
#
# Candidates:
#   agy       — Antigravity CLI via the delegation wrapper (subscription lane)
#   deepseek  — Hermes agent on deepseek-chat (the production orchestrator model)
# Tasks: sb1_pipeline, bk14_demo, bk12_wgsl_tier (all closed rows, oracle-gated)
#
# Sequential by design: earlier in this session, two unattended things sharing the
# GPU muddied a measurement, and the harness must not race itself on the scratch dir.
set -uo pipefail

REPO=/home/jericho/projects/zion/projects/visual_audio
cd "$REPO" || exit 1

AGY_CMD='REPO=$PWD bash ~/.hermes/scripts/agy_implement.sh -f {brief}'
DS_CMD='hermes -z "$(cat {brief})" -m deepseek-chat --provider custom:deepseek --yolo'

run_one () {
    local task="$1" label="$2" cmd="$3"
    echo "### $(date +%H:%M:%S)  task=$task  candidate=$label"
    timeout 3000 /usr/bin/python3 tools/builder_eval/run_eval.py \
        --task "$task" --label "$label" --candidate-cmd "$cmd" 2>&1 | \
        grep -E "GATE=|candidate exit=|INVALID|recorded" | head -4
    echo
}

for task in sb1_pipeline bk14_demo bk12_wgsl_tier; do
    run_one "$task" "agy" "$AGY_CMD"
done

for task in sb1_pipeline bk14_demo bk12_wgsl_tier; do
    run_one "$task" "deepseek" "$DS_CMD"
done

echo "### matrix complete $(date +%H:%M:%S)"
/usr/bin/python3 - <<'PY'
import json, pathlib
rows = [json.loads(l) for l in pathlib.Path('tools/builder_eval/results.jsonl').read_text().splitlines() if l.strip()]
print(f"{'task':16s} {'label':10s} {'pass':5s} {'invalid':7s} {'wall_s':>7s}")
for r in rows:
    if r.get('mode') == 'candidate':
        print(f"{r.get('task','?'):16s} {r.get('label','?'):10s} {str(r.get('gate_pass')):5s} "
              f"{str(r.get('invalid', False)):7s} {str(r.get('wall_s','-')):>7s}")
PY
