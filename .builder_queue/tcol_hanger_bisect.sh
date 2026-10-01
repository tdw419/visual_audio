#!/usr/bin/env bash
# TEST-COL-1 hanger bisect — per-file pytest collection with a hard timeout.
# Purpose: produce the measured list of files/dirs whose collection does not terminate,
# so the held pytest.ini testpaths can be declared bounded (REPAIR_PENDING_testcol1_sweep_scope.md).
# Pure measurement: writes only output/TESTCOL1_hanger_bisect.txt.
set -u
cd /home/jericho/projects/zion/projects/visual_audio
OUT=output/TESTCOL1_hanger_bisect.txt
LIST=/tmp/tcol_cands.txt
TMO=${TMO:-12}
: > "$OUT"
{
  echo "# TEST-COL-1 hanger bisect (per-file, timeout ${TMO}s)"
  echo "# cmd: /usr/bin/python3 -m pytest --collect-only -q <file>"
  echo "# started: $(date -Is)  head: $(git rev-parse --short HEAD)"
} >> "$OUT"
while read -r f; do
  [ -z "$f" ] && continue
  start=$SECONDS
  timeout "$TMO" /usr/bin/python3 -m pytest --collect-only -q "$f" > /tmp/tcol_one.txt 2>&1
  rc=$?
  dur=$((SECONDS - start))
  case $rc in
    0)   st=OK ;;
    124) st=HANG ;;
    5)   st=NOCOLLECT ;;
    *)   st=ERR$rc ;;
  esac
  echo "$st ${dur}s $f" >> "$OUT"
done < "$LIST"
echo "# finished: $(date -Is)" >> "$OUT"
echo "SUMMARY:"
grep -c HANG "$OUT" || true
grep HANG "$OUT"
