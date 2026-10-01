#!/usr/bin/env bash
# GP-4 SELF-OBSERVATION legs (brief: .builder_queue/brief_gp4_self_observation.md)
# All legs, exit 0 only on full pass. No rm anywhere. Raw per-leg output in
# corpus_build/gp4/; this script prints VERDICTS only.
# Traps honored (brief_gp1 trap table): hermes_run ~60s timeout -> split tasks,
# never widen; >=35s settle after guest writes (journal fold ~34s floor);
# verify with EXPLICIT sha (the file: sha256s format needs '<hash> <name>'
# lines — bare-nonce files trip its parser, measured 2026-09-17).
set -u
REPO=/home/jericho/projects/zion/projects/visual_audio
cd "$REPO"
PY=/usr/bin/python3
OUT=corpus_build/gp4
mkdir -p "$OUT"
TS=$(date +%s)
GB="python3 guest_bridge.py"
LOC="$PY tools/pixel_container/locate_in_container.py"
FAIL=0
note(){ echo "[$(date +%H:%M:%S)] $*"; }
die(){ echo "VERDICT: FAIL — $*"; FAIL=1; }
ok(){ echo "VERDICT: PASS — $*"; }
settle(){ note "settle ${1}s (journal fold floor)"; sleep "$1"; }

GDIR="/var/tmp/gp4_$TS"
N1="GP4N1-$TS"
N2="GP4N2-$TS"
LOG_TXT="$OUT/selflog_expected.txt"
SNAP_TXT="$OUT/snapshot_expected.txt"

# ---------- L1a: guest writes /proc/self snapshot + nonce1 (ONE small task) ----------
note "L1a: guest /proc/self introspection task"
L1_PROMPT="mkdir -p $GDIR && { echo \"== GP4 SELF-OBSERVATION $TS ==\"; grep -E '^(Name|Pid|PPid|Umask|Threads|TracerPid):' /proc/self/status; echo '-- fd --'; ls -l /proc/self/fd 2>/dev/null | head -8; } > $GDIR/proc_snapshot.txt 2>&1; echo $N1 > $GDIR/nonce1.txt; echo $N1 >> $GDIR/self_log.txt; echo DONE-$TS"
L1_OUT=$($GB hermes_run "$L1_PROMPT" 2>&1)
echo "$L1_OUT" > "$OUT/l1_guest_transcript_raw.txt"
grep -q "✅ Success" <<<"$L1_OUT" && ok "L1a: guest task succeeded" || die "L1a: guest task failed — see $OUT/l1_guest_transcript_raw.txt"

# ---------- L1b: host fetches the /proc snapshot through the bridge ----------
settle 36
note "L1b: read back snapshot + nonce via guest cat"
SNAP_GUEST=$($GB read_file "$GDIR/proc_snapshot.txt" 2>/dev/null || echo __BRIDGE_NO_READ__)
if grep -q "__BRIDGE_NO_READ__" <<<"$SNAP_GUEST"; then
  # bridge read_file failed: fall back to hermes_run cat (slower but honest)
  SNAP_GUEST=$($GB hermes_run "cat $GDIR/proc_snapshot.txt" 2>&1)
fi
echo "$SNAP_GUEST" > "$OUT/l1b_snapshot_via_bridge_raw.txt"
grep -q "GP4 SELF-OBSERVATION" "$OUT/l1b_snapshot_via_bridge_raw.txt" \
  && ok "L1b: /proc/self snapshot round-tripped through bridge" \
  || die "L1b: snapshot content missing — $(head -5 "$OUT/l1b_snapshot_via_bridge_raw.txt")"

# ---------- container presence + geometry ----------
note "L1c: container-side locate of the three files"
$LOC locate "$GDIR/proc_snapshot.txt" > "$OUT/l2_locate_snapshot.json" 2>&1
$LOC locate "$GDIR/nonce1.txt"       > "$OUT/l2_locate_nonce1.json" 2>&1
$LOC locate "$GDIR/self_log.txt"     > "$OUT/l2_locate_selflog.json" 2>&1
for f in l2_locate_snapshot l2_locate_nonce1 l2_locate_selflog; do
  grep -q '"extents": *1' "$OUT/$f.json" && ok "$f: present, single-extent" \
    || die "$f: geometry — $(head -3 "$OUT/$f.json")"
done

# ---------- RED-A: wrong-sha verify must REJECT ----------
note "RED-A: wrong-sha verify on proc_snapshot must report match:false"
WRONGSHA=$(printf '0%.0s' $(seq 64))
$LOC verify "$GDIR/proc_snapshot.txt" "$WRONGSHA" > "$OUT/red_a_wrongsha_verify.json" 2>&1
grep -q '"match": *false' "$OUT/red_a_wrongsha_verify.json" \
  && ok "RED-A: wrong sha rejected (match:false — gate can fail)" \
  || die "RED-A: wrong-sha verify did NOT reject — $(head -3 "$OUT/red_a_wrongsha_verify.json")"

# ---------- L2: byte-exact closure via EXPLICIT sha ----------
# The container bytes must hash to the sha of the content the GUEST was
# instructed to write — computed host-side from the literal, not copied from
# the guest's own sha256sum (that would let a lying guest self-certify).
note "L2: explicit-sha verify (nonce1 + self_log nonce1-only)"
printf '%s\n' "$N1" > "$OUT/l2_nonce1_literal.txt"
SHA_N1=$($PY -c "import hashlib,sys;print(hashlib.sha256(open('$OUT/l2_nonce1_literal.txt','rb').read()).hexdigest())")
$LOC verify "$GDIR/nonce1.txt" "$SHA_N1" > "$OUT/l2_verify_nonce1.json" 2>&1
grep -q '"match": *true' "$OUT/l2_verify_nonce1.json" \
  && ok "L2: nonce1 byte-exact in container (match:true — closure)" \
  || die "L2: nonce1 verify — $(head -5 "$OUT/l2_verify_nonce1.json")"
printf '%s\n' "$N1" > "$LOG_TXT"
SHA_LOG1=$($PY -c "import hashlib;print(hashlib.sha256(open('$LOG_TXT','rb').read()).hexdigest())")
$LOC verify "$GDIR/self_log.txt" "$SHA_LOG1" > "$OUT/l2_verify_selflog_pre.json" 2>&1
grep -q '"match": *true' "$OUT/l2_verify_selflog_pre.json" \
  && ok "L2: self_log pre-state byte-exact" \
  || die "L2: self_log pre-state verify — $(head -5 "$OUT/l2_verify_selflog_pre.json")"
PSIZE=$($PY -c "import json;print(json.load(open('$OUT/l2_locate_selflog.json'))['size'])" 2>/dev/null || echo -1)

# ---------- L3: the log GROWS in pixel space ----------
note "L3: second nonce append → growth visible in pixel space"
L3_OUT=$($GB hermes_run "echo $N2 >> $GDIR/self_log.txt; echo APPENDED-$TS" 2>&1)
echo "$L3_OUT" > "$OUT/l3_guest_append_raw.txt"
grep -q "✅ Success" <<<"$L3_OUT" && ok "L3: append dispatched" || die "L3: append failed — $(head -3 "$OUT/l3_guest_append_raw.txt")"
settle 36
$LOC locate "$GDIR/self_log.txt" > "$OUT/l3_locate_post.json" 2>&1
SSIZE=$($PY -c "import json;print(json.load(open('$OUT/l3_locate_post.json'))['size'])" 2>/dev/null || echo -1)
# RED-B (non-vacuity): pre-state sha must be REJECTED against the grown file
SHA_LOG1_REUSED=$SHA_LOG1
$LOC verify "$GDIR/self_log.txt" "$SHA_LOG1_REUSED" > "$OUT/red_b_presha_vs_post.json" 2>&1
grep -q '"match": *false' "$OUT/red_b_presha_vs_post.json" \
  && ok "RED-B: pre-append sha rejected against grown log (match:false — checker discriminates)" \
  || die "RED-B: checker cannot discriminate (unexpected match:true) — $(head -3 "$OUT/red_b_presha_vs_post.json")"
printf '%s\n%s\n' "$N1" "$N2" > "$LOG_TXT"
SHA_LOG2=$($PY -c "import hashlib;print(hashlib.sha256(open('$LOG_TXT','rb').read()).hexdigest())")
$LOC verify "$GDIR/self_log.txt" "$SHA_LOG2" > "$OUT/l3_verify_selflog.json" 2>&1
grep -q '"match": *true' "$OUT/l3_verify_selflog.json" \
  && ok "L3: both nonces byte-exact in container post-append" \
  || die "L3: post-append verify — $(head -5 "$OUT/l3_verify_selflog.json")"
[ "$SSIZE" -gt "$PSIZE" ] && ok "L3: pixel-side size grew $PSIZE → $SSIZE bytes" \
  || die "L3: size did not grow ($PSIZE → $SSIZE)"
echo "{\"ts\":$TS,\"gdir\":\"$GDIR\",\"pre_size\":$PSIZE,\"post_size\":$SSIZE,\"nonce1\":\"$N1\",\"nonce2\":\"$N2\",\"sha_log_pre\":\"$SHA_LOG1\",\"sha_log_post\":\"$SHA_LOG2\"}" > "$OUT/l3_growth_summary.json"

# ---------- summary ----------
if [ $FAIL -eq 0 ]; then
  echo "GATE: GP4 ALL LEGS GREEN (dir=$OUT ts=$TS)"
  exit 0
else
  echo "GATE: GP4 RED (dir=$OUT ts=$TS)"
  exit 1
fi
