#!/bin/bash
# SUITE-HEAVY-1 solo re-measurement (orchestrator, 2026-09-13). Sequential, one file at a time.
cd /home/jericho/projects/zion/projects/visual_audio || exit 1
OUT=/tmp/suite_heavy1_solo_20260913.txt
: > "$OUT"
echo "# SUITE-HEAVY-1 solo re-measurement $(date -Is)" >> "$OUT"
echo "# interpreter: /usr/bin/python3 ; cmd per file: timeout 240 /usr/bin/python3 -m pytest <f> -q -p no:randomly" >> "$OUT"
for f in tests/test_probe_stval.py tests/test_gh20_fs_v2.py tests/test_spatial_rv32i_cpu.py tests/test_sbi_firmware.py tests/test_rv64i_to_glyph_xv6_nano.py; do
  echo "=== $f  load=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT"
  start=$(date +%s.%N)
  timeout 240 /usr/bin/python3 -m pytest "$f" -q -p no:randomly > /tmp/_solo_run.txt 2>&1
  rc=$?
  end=$(date +%s.%N)
  echo "rc=$rc wall=$(/usr/bin/python3 -c "print(f'{$end-$start:.2f}')")s" >> "$OUT"
  tail -3 /tmp/_solo_run.txt >> "$OUT"
  echo "" >> "$OUT"
done
echo "DONE $(date -Is)" >> "$OUT"
