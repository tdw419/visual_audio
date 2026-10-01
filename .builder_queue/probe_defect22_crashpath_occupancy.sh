#!/bin/bash
# FIXED occupancy sampler (the first version exited immediately: the watcher was launched
# before its .running flag existed, so samples.txt was empty and the "none observed" result
# was VACUOUS). This version: touch the flag first, have a planted-report positive control,
# sample every 0.25 s, and count apport refusals in the run's own log window.
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
CRASH=/var/crash; Q=/tmp/d22_window2; mkdir -p "$Q"
is_fixture() { grep -a -m 1 '^ProcCmdline:' "$1" 2>/dev/null | grep -qa faulthandler_segv_fixture.py; }

# clean entry
for f in "$CRASH"/*.crash; do [ -f "$f" ] || continue; mv "$f" "$Q/entry_$(basename "$f").$(date +%s)" 2>/dev/null; done

# positive control: plant a fixture report; the sampler must be able to see it
printf 'ProblemType: Crash\nExecutablePath: /usr/bin/python3.12\nProcCmdline: /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py --planted-control\n' > "$CRASH/_usr_bin_python3.12.1000.crash"
echo "planted control: $(ls "$CRASH"/*.crash | wc -l) report(s), fixture=$(is_fixture "$CRASH/_usr_bin_python3.12.1000.crash" && echo yes || echo no)"

LOGLINES0=$(wc -l < /var/log/apport.log)
touch "$Q/.running"
( i=0; while [ -f "$Q/.running" ]; do
    n=0; fx=0
    for f in "$CRASH"/*.crash; do [ -f "$f" ] || continue; n=$((n+1)); is_fixture "$f" && fx=$((fx+1)); done
    echo "$(date +%s.%N) $n $fx"; i=$((i+1)); sleep 0.25
  done ) > "$Q/samples.txt" &
WP=$!
( bash tools/gate_arc_lega_capture.sh 2>&1 | while IFS= read -r l; do printf '%s %s\n' "$(date +%s.%N)" "$l"; done ) > "$Q/gate_ts.log"
rm -f "$Q/.running"; wait $WP 2>/dev/null
echo "== sampler: $(wc -l < "$Q/samples.txt") samples, max fx=$(awk 'BEGIN{m=0}{if($3>m)m=$3}END{print m}' "$Q/samples.txt") =="

python3 - "$Q" <<'EOF'
import sys, re
q = sys.argv[1]
S = [l.split() for l in open(f"{q}/samples.txt") if l.strip()]
assert S, "sampler produced no samples (vacuous)"
t0 = float(S[0][0])
legs = [(float(m.group(1)), m.group(2)) for m in
        (re.match(r"(\d+\.\d+) -- (.*)", l.rstrip()) for l in open(f"{q}/gate_ts.log")) if m]
occ = [float(s[0]) - t0 for s in S if int(s[2]) > 0]
print(f"== leg timeline (s from first sample; {len(S)} samples over {float(S[-1][0])-t0:.1f}s) ==")
for t, n in legs: print(f"   {t-t0:6.2f}s  {n[:78]}")
if not occ:
    print("== fixture occupancy: NONE (control planted -> would mean the sampler is blind) ==")
else:
    runs, start, prev = [], occ[0], occ[0]
    for t in occ[1:]:
        if t - prev > 0.6: runs.append((start, prev)); start = t
        prev = t
    runs.append((start, prev))
    for a, b in runs: print(f"   fixture report present {a:6.2f}s -> {b:6.2f}s  (~{b-a+0.25:.2f}s)")
    print(f"   total fixture-occupied seconds: {len(occ)*0.25:.2f}s over {len(runs)} window(s)")
    first = runs[0][0]
    near = [n for t, n in legs if -0.5 <= t - t0 - first <= 6]
    print(f"   first window opens at/near leg: {near}")
EOF
echo "== apport log delta for this run =="
tail -n +$((LOGLINES0+1)) /var/log/apport.log | cut -c1-135
echo "== refusals in this run: $(tail -n +$((LOGLINES0+1)) /var/log/apport.log | grep -c 'already exists and unseen') =="
echo "== final /var/crash count = $(ls "$CRASH"/*.crash 2>/dev/null | wc -l) =="
