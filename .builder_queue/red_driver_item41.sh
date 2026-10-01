#!/usr/bin/env bash
# item-41 RED-leg driver: apply mutation, run gate (expect FAIL), restore byte-exact.
# Usage: bash .builder_queue/red_driver_item41.sh 1|2
set -u
cd "$(dirname "$0")/.."
LEG="$1"
MD5_GREEN=$(md5sum tools/glyph_taskmgr.py | cut -d' ' -f1)
cp tools/glyph_taskmgr.py /tmp/taskmgr_green_item41.py

python3 - "$LEG" <<'PYEOF'
import sys
leg = sys.argv[1]
p = 'tools/glyph_taskmgr.py'
src = open(p).read()
if leg == '1':
    # RED 1: run_ready() ignores the paused state -> T3 must fail
    old = '''            pid = info["pid"]
            if pid in self._paused:
                continue                     # paused: skipped, not run
            task = self._require_pid(pid)'''
    new = '''            pid = info["pid"]
            task = self._require_pid(pid)'''
elif leg == '2':
    # RED 2: kill() marks EXIT_OK instead of EXIT_FAULT -> T2 must fail
    old = '''        task["exit_status"] = EXIT_FAULT
        task["state"] = STATE_EXITED

    def run_ready'''
    new = '''        task["exit_status"] = EXIT_OK
        task["state"] = STATE_EXITED

    def run_ready'''
else:
    sys.exit("leg must be 1 or 2")
assert old in src, "mutation anchor not found"
open(p, 'w').write(src.replace(old, new))
print(f"RED{leg} mutation applied")
PYEOF
PY_STATUS=$?

if [ "$PY_STATUS" -eq 0 ]; then
  PYTHONPATH=. python3 -m pytest tests/test_item41_taskmgr.py -q 2>&1 | tail -6
  echo "RED${LEG}_GATE_EXIT=${PIPESTATUS[0]}"
else
  echo "MUTATION FAILED rc=$PY_STATUS"
fi

cp /tmp/taskmgr_green_item41.py tools/glyph_taskmgr.py
MD5_AFTER=$(md5sum tools/glyph_taskmgr.py | cut -d' ' -f1)
echo "MD5 green=$MD5_GREEN restored=$MD5_AFTER"
[ "$MD5_GREEN" = "$MD5_AFTER" ] && echo "RESTORE_BYTE_EXACT" || echo "RESTORE_MISMATCH"
