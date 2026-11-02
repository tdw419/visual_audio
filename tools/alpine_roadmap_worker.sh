#!/usr/bin/env bash
# One iteration of the Alpine-emulator roadmap loop.
#
# IMPORTANT: this script dispatches glm-4.7 (via hermes) to do the EDIT only.
# It never trusts glm-4.7's own claim of success. glm-4.7 via hermes has
# fabricated detailed, plausible-looking evidence (kernel panic traces, a
# "VCC PASSED" test result) in this exact project twice before -- see
# memory hermes-fabricated-panic-trace. Every acceptance criterion here is
# re-checked from a real command/file by this script or by the calling
# Claude Code session, never accepted from the worker's chat output.
set -euo pipefail
cd "$(dirname "$0")/.."

ROADMAP=alpine_emulator_roadmap.yaml
HEARTBEAT=/tmp/alpine_roadmap_loop_heartbeat

write_heartbeat() {
  # status: starting | dispatched | done | failed
  printf 'ts=%s pid=%s status=%s task=%s\n' \
    "$(date -u +%FT%TZ)" "$$" "$1" "${TASK_ID:-none}" > "$HEARTBEAT"
}
trap 'write_heartbeat failed' ERR
write_heartbeat starting

eval "$(python3 - "$ROADMAP" <<'PY'
import sys, shlex
from roadmap_builder import parse_yaml
r = parse_yaml(sys.argv[1])
t = r.next_task()
if t is None:
    print("TASK_ID=")
    sys.exit(0)
print(f"TASK_ID={shlex.quote(t.id)}")
print(f"TASK_TITLE={shlex.quote(t.title)}")
print(f"TASK_FILES={shlex.quote(', '.join(t.files))}")
print(f"TASK_DESC={shlex.quote(t.description)}")
print(f"TASK_AC={shlex.quote(' | '.join(t.acceptance_criteria))}")
PY
)"

if [ -z "${TASK_ID:-}" ]; then
  write_heartbeat done
  echo "No actionable task (all done, or blocked on unmet dependencies)."
  exit 0
fi

echo "=== Next task ==="
echo "ID: $TASK_ID"
echo "Title: $TASK_TITLE"
echo "Files: $TASK_FILES"
echo "Description: $TASK_DESC"
echo "Acceptance criteria: $TASK_AC"
echo "=================="

PROMPT="You are working in $(pwd) on the RISC-V GPU emulator SPATIAL_RV64I.wgsl \
(Alpine Linux boot). Your ONLY job right now is this single roadmap task:

Task ID: ${TASK_ID}
Title: ${TASK_TITLE}
Target files: ${TASK_FILES}

Read alpine_emulator_roadmap.yaml for full task description and acceptance
criteria (search for the task ID). Make the minimal code change needed to
satisfy it. Do NOT claim the task is verified, tested, or passing -- you do
not have the authority to mark anything done. Just make the change, run any
quick local check you can (e.g. does the shader still parse), and report
exactly what you changed and why, with no invented log/trace/panic output.
If you did not actually run something, say you did not run it."

write_heartbeat dispatched
echo "=== Dispatching glm-4.7 via hermes ==="
hermes -z "$PROMPT" -m glm-4.7 --yolo | tee "/tmp/hermes_task_${TASK_ID}.log"
write_heartbeat done
echo "=== glm-4.7 done. NOT trusting its report. ==="
echo "Next: the supervising Claude Code session must independently re-run"
echo "the task's stated validation command and read raw output before"
echo "editing ${ROADMAP} to mark ${TASK_ID} done."
