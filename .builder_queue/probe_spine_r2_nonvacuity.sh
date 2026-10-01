#!/usr/bin/env bash
# probe_spine_r2_nonvacuity.sh — out-of-tree non-vacuity probe for SPINE-R2-WIREIN.
# Mutates the LIVE module twice (restoring byte-identical between probes) to show the
# gate's legs can actually go RED. Never leaves the tree modified (md5-verified at the end).
set -uo pipefail
cd /home/jericho/projects/zion/projects/visual_audio
OUT=output/spine_r2_nonvacuity_probe.txt
EMIT=tools/geos_emit.py
BACKUP=/tmp/geos_emit.spine_r2.bak.py

cp -f "$EMIT" "$BACKUP"
MD5_0=$(md5sum "$EMIT" | awk '{print $1}')
echo "baseline md5=$MD5_0"

run_gate () { /usr/bin/python3 -m pytest tests/test_spine_r2_wirein.py -q 2>&1 | tail -2; }

echo "--- GATE AT BASELINE (expect 6 passed) ---"
run_gate

echo "--- PROBE A: drop the unattributed flag (expect leg 1 RED) ---"
/usr/bin/python3 - "$EMIT" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
needle = 'meta["unattributed"] = True'
assert s.count(needle) == 1, f"needle count {s.count(needle)}"
p.write_text(s.replace(needle, 'pass  # PROBE-A neutered flag'))
print("PROBE-A applied")
PY
run_gate
cp -f "$BACKUP" "$EMIT"
echo "restored md5=$(md5sum "$EMIT" | awk '{print $1}')"

echo "--- PROBE B: skip the registry append (expect leg 2 RED) ---"
/usr/bin/python3 - "$EMIT" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
needle = 'reg.register(rec, origin_id=orig_id)'
assert s.count(needle) == 1, f"needle count {s.count(needle)}"
p.write_text(s.replace(needle, 'pass  # PROBE-B neutered append'))
print("PROBE-B applied")
PY
run_gate
cp -f "$BACKUP" "$EMIT"
MD5_1=$(md5sum "$EMIT" | awk '{print $1}')
echo "final md5=$MD5_1"
if [[ "$MD5_0" == "$MD5_1" ]]; then echo "RESTORE OK (byte-identical)"; else echo "RESTORE FAILED"; exit 3; fi
echo "--- GATE AFTER RESTORE (expect 6 passed) ---"
run_gate
