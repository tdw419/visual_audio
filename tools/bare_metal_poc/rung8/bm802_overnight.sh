#!/usr/bin/env bash
# BM802 overnight driver: run the fault-sensitivity sweep to completion without
# an agent awake to babysit it.
#
# Why a driver and not one long command: the map is ~193 boots (~2 h), longer
# than any agent session reliably lives. The sweep is append-only and takes
# --resume, so the expensive part survives a crash; this file survives the
# session by being started under setsid+nohup, and survives the machine going
# to sleep because systemd-inhibit holds the sleep lock for its lifetime.
#
#   launch: setsid nohup systemd-inhibit --mode=block --what=sleep \
#             --who=BM802 --why="fault-sensitivity sweep, ~2h of serial boots" \
#             bash bm802_overnight.sh > /tmp/bm802_overnight.out 2>&1 &
#
# Artifacts: bm802_overnight.log (progress), bm802_sweep_rows.txt (one JSON row
# per boot), bm802_sensitivity_map.txt (the map), BM802_RUN_STATUS.txt (the
# verdict line an agent reads first).
set -u
cd "$(dirname "$0")" || exit 1
LOG=bm802_overnight.log
STATUS=BM802_RUN_STATUS.txt
PIDF=/tmp/bm802_overnight.pid
MIN_FREE_MB=1200            # one sample medium is 13.6 MB; the box has 4 GB left
MAX_TRIES=14

say() { printf '%s %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

# one driver at a time: two resume-loops would both queue on the lane and both
# append rows, which is exactly the interleaved-boot failure BM903 measured.
if [[ -f $PIDF ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  say "ABORT: driver pid $(cat "$PIDF") already alive"; exit 1
fi
echo $$ > "$PIDF"

free_mb=$(df -Pm / | awk 'NR==2{print $4}')
if (( free_mb < MIN_FREE_MB )); then
  say "ABORT: only ${free_mb} MB free on /; the sweep writes a 13.6 MB medium per boot"
  exit 1
fi
say "start: pid $$, ${free_mb} MB free, up to $MAX_TRIES resume attempts"

# The fixture is the sweep's premise: if the gate-off rig is broken the whole
# map measures nothing, so fail before the first boot rather than after 2 hours.
if ! python3 bm802_fixture.py >> "$LOG" 2>&1; then
  say "ABORT: fixture selftest red -- no boots spent"; exit 1
fi
say "fixture green; starting sweep"

rc=1
for try in $(seq 1 "$MAX_TRIES"); do
  say "attempt $try: run_bm802_sweep.py --resume"
  python3 run_bm802_sweep.py --resume >> "$LOG" 2>&1
  rc=$?
  rows=$(grep -c '^{' bm802_sweep_rows.txt 2>/dev/null); rows=${rows:-0}
  say "attempt $try exit $rc; $rows rows on disk"
  [[ $rc -eq 0 ]] && break
  # non-zero after the lane never cleared, or a host-side assert: pause long
  # enough for another session's boots to finish, then continue from the rows.
  sleep 60
done

# Regenerate the map even on failure: a partial map labelled PARTIAL is
# interpretable, a missing one is not.
python3 run_bm802_sweep.py --resume --summary-only >> "$LOG" 2>&1
rows=$(grep -c '^{' bm802_sweep_rows.txt 2>/dev/null); rows=${rows:-0}
planned=$(python3 -c 'import run_bm802_sweep as s; r=s.Rig(); print(len(s.plan(r)))' 2>/dev/null || echo '?')
if [[ $rc -eq 0 ]]; then
  say "DONE: $rows/$planned boots, map written"
else
  say "PARTIAL after $MAX_TRIES attempts: $rows/$planned rows -- read the map with suspicion"
fi
{ printf 'BM802 sweep %s at %s\n' "$([[ $rc -eq 0 ]] && echo DONE || echo PARTIAL)" "$(date -Is)"
  printf 'rows=%s planned=%s rc=%s\n' "$rows" "$planned" "$rc"
  printf 'next: read bm802_sensitivity_map.txt, then land the receipt + ROADMAP cell\n'
} > "$STATUS"
say "status written: $(head -1 "$STATUS")"
exit $rc
