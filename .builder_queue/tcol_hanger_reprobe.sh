#!/usr/bin/env bash
# TEST-COL-1 second pass: re-probe only the files that exceeded the 12s bisect timeout,
# with a 60s timeout, to separate "slow but terminates" from "does not terminate".
set -u
cd /home/jericho/projects/zion/projects/visual_audio
SRC=output/TESTCOL1_hanger_bisect.txt
OUT=output/TESTCOL1_hanger_reprobe60.txt
: > "$OUT"
{
  echo "# TEST-COL-1 hanger re-probe (timeout 60s) for files flagged at 12s"
  echo "# cmd: /usr/bin/python3 -m pytest --collect-only -q <file>"
  echo "# started: $(date -Is)  head: $(git rev-parse --short HEAD)"
} >> "$OUT"
grep '^HANG ' "$SRC" | awk '{print $3}' > /tmp/tcol_hangs.txt
while read -r f; do
  [ -z "$f" ] && continue
  start=$SECONDS
  timeout 60 /usr/bin/python3 -m pytest --collect-only -q "$f" > /tmp/tcol_one2.txt 2>&1
  rc=$?
  dur=$((SECONDS - start))
  case $rc in
    0)   st=OK ;;
    124) st=NOTERM60 ;;
    5)   st=NOCOLLECT ;;
    *)   st=ERR$rc ;;
  esac
  echo "$st ${dur}s $f" >> "$OUT"
done < /tmp/tcol_hangs.txt
echo "# finished: $(date -Is)" >> "$OUT"
