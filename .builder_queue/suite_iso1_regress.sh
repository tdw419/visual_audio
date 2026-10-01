#!/usr/bin/env bash
# SUITE-ISO-1 L4 no-regression: arc leg B + leg A at the SUITE-ISO-1 working tree
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
echo "=== collect-only 'ERROR' lines (should be none) ==="
grep -n "ERROR" output/suite_iso1_collect_only.txt | head -5
echo "(end)"

echo "=== leg B ==="
timeout 200 /usr/bin/python3 -m pytest tests/test_osskel_*.py tests/test_substor_*.py \
  tests/test_obs1_*.py tests/test_wf1_*.py tests/test_spatial_rv32i_cpu.py \
  -q --junitxml=output/arc_legB_suite_iso1.xml > output/arc_legB_suite_iso1.txt 2>&1
echo "LEG_B_RC=$?"
tail -2 output/arc_legB_suite_iso1.txt

echo "=== leg A (52 files) ==="
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
timeout 500 /usr/bin/python3 -m pytest $FILES -q --junitxml=output/arc_verify_suite_iso1.xml > output/arc_legA_suite_iso1.txt 2>&1
echo "LEG_A_RC=$?"
grep -c 'Fatal Python error' output/arc_legA_suite_iso1.txt
tail -3 output/arc_legA_suite_iso1.txt
