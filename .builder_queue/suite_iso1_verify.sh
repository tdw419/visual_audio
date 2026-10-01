#!/usr/bin/env bash
# SUITE-ISO-1 verification: hold-out RED leg + collect-only no-regression + scope check
# (builder cron af3e62239ce2, 2026-09-13)
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9

echo "=== A. HOLD-OUT RED (gate must be red with the module absent) ==="
mv tests/test_suite_iso_harness.py /tmp/held_gate_suite_iso1.py
mv tools/suite_iso_harness.py /tmp/held_tools_suite_iso1.py
timeout 120 /usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q > output/suite_iso1_gate_RED_holdout.txt 2>&1
echo "HOLDOUT_RC=$?"
tail -2 output/suite_iso1_gate_RED_holdout.txt
mv /tmp/held_gate_suite_iso1.py tests/test_suite_iso_harness.py
mv /tmp/held_tools_suite_iso1.py tools/suite_iso_harness.py
echo "restored: $(ls -l tests/test_suite_iso_harness.py tools/suite_iso_harness.py | wc -l) files"

echo "=== B. collect-only sweep must stay rc=0 / zero errors ==="
timeout 240 /usr/bin/python3 -m pytest tests/ --collect-only -q > output/suite_iso1_collect_only.txt 2>&1
echo "COLLECT_RC=$?"
tail -2 output/suite_iso1_collect_only.txt
grep -ci "^ERROR\|errors" output/suite_iso1_collect_only.txt

echo "=== C. scope check: tracked-dirty must be empty ==="
git status --short | grep -v '^??' | head -10
echo "(end tracked-dirty)"
