#!/usr/bin/env bash
# run_bm602_e2e.sh -- Rung 6, TASK_BM602: does a medium that repairs itself
# still boot, and does the gate still refuse what it cannot repair?
#
# Every boot leg compares the serial wire against bm602_fixtures.json, written
# by bm602_mkimg.py from its own host replay BEFORE any qemu ran. Nothing here
# contains an expected number: the script asks, the fixture file answers.
#
# Budgets come from BM903's measured race survey, not from a guess: Tiny Core's
# autologin wins the tty1/ttyS0 argument about half the time, so an anchor leg
# gets up to $BOOT_ATTEMPTS boots of $ATTEMPT_TIMEOUT s each -- the same worst
# case the single longer timeout had. A leg that gets a LOADER line wrong is
# not retried at all; bm602_gate.py refuses to re-roll a deterministic die.
set -u
cd "$(dirname "$0")"
OUT=logs
mkdir -p "$OUT"
RE=${1:-}                              # pass --resume to skip green legs
pass=0; fail=0; skipped=0
ok()   { echo "  [PASS] $1"; pass=$((pass+1)); }
bad()  { echo "  [RED ] $1"; fail=$((fail+1)); }
hr()   { echo "----------------------------------------------------------------"; }
# --resume must read the recorded EXIT CODE, not the word GREEN. Its first pass
# caught this file lying: the identity stage's status line is
# `identity rc=1 IDENTITY: GREEN 20  RED 6` -- both verdicts in one line -- so
# `grep -q GREEN` called a RED stage already done and skipped it. A guard that
# can be satisfied by the word it is judging is not a guard.
was_green() {                          # was_green <status stem>
  [[ "$RE" == "--resume" && -f "$OUT/$1.status" ]] && grep -q " rc=0 " "$OUT/$1.status"
}
run_leg() {                            # run_leg <fixture>
  local f=$1
  if was_green "$f"; then
    ok "$f already GREEN on a previous run (--resume)"; skipped=$((skipped+1)); return 0
  fi
  python3 bm602_gate.py "$f" --attempts $BOOT_ATTEMPTS --budget $ATTEMPT_TIMEOUT \
      > "$OUT/$f.log" 2>&1
  local rc=$?
  echo "$f rc=$rc $(grep -m1 "^$f:" "$OUT/$f.log" || echo 'no verdict line')" \
    | tee "$OUT/$f.status"
  if [[ $rc -eq 0 ]]; then ok "$f"; else bad "$f"; sed 's/^/        /' "$OUT/$f.log"; fi
  return 0
}

BOOT_ATTEMPTS=8
ATTEMPT_TIMEOUT=45

hr; echo "STATIC 1-3: codec, asserted delta list, assemble + host replay"
python3 bm602_pxcodec.py > "$OUT/s1_codec.log" 2>&1 \
  && ok "codec: 7 planes carry the landed PXC1 payload; corrector selftest green" \
  || { bad "codec"; cat "$OUT/s1_codec.log"; }
python3 bm602_construct.py > "$OUT/s2_construct.log" 2>&1 \
  && ok "loader forked from rung9 by asserted deltas: $(grep -m1 stage2: "$OUT/s2_construct.log")" \
  || { bad "construct: a delta stopped matching, or the deltas are not invertible"; cat "$OUT/s2_construct.log"; }
python3 bm602_mkimg.py > "$OUT/s3_mkimg.log" 2>&1 \
  && ok "medium built: $(tail -1 "$OUT/s3_mkimg.log")" \
  || { bad "mkimg: nasm or the host replay failed"; tail -25 "$OUT/s3_mkimg.log"; }
# A fixture the gate will compare against must exist before the gate runs, and
# the corrupt-medium control is produced by rung9's OWN predictor, not this one.
python3 ../rung9/bm903_px_corrupt.py ../rung9/bm903_medium_px.raw \
        fixtures/bm903_medium_px_corrupt.raw 4000000 \
     > "$OUT/s4_bm903_corrupt.log" 2>&1 \
  && ok "BM903 corrupt control: $(tail -1 "$OUT/s4_bm903_corrupt.log")" \
  || { bad "could not build the BM903 corrupt control"; cat "$OUT/s4_bm903_corrupt.log"; }

hr; echo "BOOT 1-3: the three legs that decide inside a second"
run_leg pxc1_front_end
run_leg two_symbol_collision
# The quieter refusal: three equal faults give all-zero syndromes, so the
# corrector prints ECC=0 PAR=0 -- the clean medium's own counters -- on a medium
# with three wrong payload bytes. If the gate lets THIS through, ECC is not
# merely weak, it is load-bearing in the wrong direction.
run_leg blind_spot_equal_triple

hr; echo "BOOT 3-7: five damaged media that must still reach tc@box on serial"
for f in clean chunk_plane0_stuckff chunk_plane1_stuck00 \
         parity_chunk_stuckff erase_block_128k; do
  run_leg "$f"
done

hr; echo "IDENTITY: BM601 legs 1-2 strengthened -- byte-identical transcripts + handoff dumps"
# "It booted and the counters moved" is not the row's claim; "it booted
# byte-identical to the clean boot" is. This stage re-reads the transcripts the
# legs above just wrote (no re-roll, no new die) and then captures the executed
# handoff state of three of the media with the forked gdb session.
if was_green identity; then
  ok "identity stage already GREEN on a previous run"; skipped=$((skipped+1))
else
  python3 bm602_identity.py > "$OUT/identity.log" 2>&1
  rc=$?
  echo "identity rc=$rc $(grep -m1 '^IDENTITY:' "$OUT/identity.log" || echo 'no summary line')" \
    | tee "$OUT/identity.status"
  sed -n '/^  \[PASS\]\|^  \[RED \]/p' "$OUT/identity.log" | sed 's/^/        /'
  if [[ $rc -eq 0 ]]; then ok "$(grep -m1 '^IDENTITY:' "$OUT/identity.log")"
  else bad "identity: a repaired boot is not the clean boot -- see the spans above"; fi
fi

hr; echo "REGRESSION: the proven loader and its gate, in the same invocation"
# ECC must not be able to buy a boot the old gate would have refused -- so the
# old gate runs here, unchanged, against both of its own media. rung9's tree is
# a read-only input: these write only into this directory.
if was_green r9_control; then
  ok "BM903 control already GREEN on a previous run"; skipped=$((skipped+1))
else
  # The same race BM602's own anchor legs are allowed, and for the same
  # measured reason: Tiny Core's autologin reaches ttyS0 about half the time,
  # and BM903 recorded 3/8 and 5/8. Single-shot here would call a lost coin
  # flip a regression in the proven loader.
  rc=1; b=0
  for b in $(seq 1 $BOOT_ATTEMPTS); do
    python3 ../rung9/bm903_anchor_boot.py ../rung9/bm903_medium_px.raw \
        "$OUT/r9_control.log" $ATTEMPT_TIMEOUT > "$OUT/r9_control.out" 2>&1
    rc=$?
    [[ $rc -eq 0 ]] && break
    echo "      control boot $b/$BOOT_ATTEMPTS: no tc@box in ${ATTEMPT_TIMEOUT}s (guest autologin race)"
  done
  echo "bm903 clean rc=$rc boots=$b $(grep -m1 elapsed "$OUT/r9_control.out" | tail -1)" \
    | tee "$OUT/r9_control.status"
  if [[ $rc -eq 0 ]]; then ok "BM903's own pixel medium still reaches its gate and its anchor (boot $b)"
  else bad "BM903 control: $BOOT_ATTEMPTS boots of the proven medium, none reached its anchor"; tail -12 "$OUT/r9_control.out"; fi
fi
if was_green r9_corrupt; then
  ok "BM903 corrupt refusal already GREEN"; skipped=$((skipped+1))
else
  python3 ../rung9/bm903_anchor_boot.py fixtures/bm903_medium_px_corrupt.raw \
      "$OUT/r9_corrupt.log" 30 > "$OUT/r9_corrupt.out" 2>&1
  rc=$?
  pred=$(awk '{print $1}' fixtures/bm903_medium_px_corrupt.crc)
  pred_exp=$(awk '{print $2}' fixtures/bm903_medium_px_corrupt.crc)
  wire=$(sed -n 's/.*GATE2 CRC=\([0-9A-F]\{8\}\).*/\1/p' "$OUT/r9_corrupt.log" | head -1)
  wire_exp=$(sed -n 's/.*EXP=\([0-9A-F]\{8\}\).*/\1/p' "$OUT/r9_corrupt.log" | head -1)
  echo "bm903 corrupt rc=$rc predicted=$pred wire=${wire:-none}" | tee "$OUT/r9_corrupt.status"
  # rc is 1 either way for a refusing medium (no anchor is a missing check), so
  # the assertions are the ones that mean something: it named the CRC rung9's
  # own predictor derived from the file, it never built a handoff, and no
  # kernel drew a prompt.
  if [[ -n "$wire" && "$wire" == "$pred" ]] \
     && [[ "$wire_exp" == "$pred_exp" ]] \
     && ! grep -qa 'HANDOFF BUILT' "$OUT/r9_corrupt.log" \
     && ! grep -qa 'tc@box' "$OUT/r9_corrupt.log"; then
    ok "BM903 still refuses a corrupt medium, at the CRC rung9's own predictor named ($wire, EXP $wire_exp)"
  else
    bad "BM903's refusal leg moved (rc=$rc wire=${wire:-none}/$wire_exp predicted=$pred/$pred_exp)"; tail -12 "$OUT/r9_corrupt.out"
  fi
fi

hr
echo "GREEN $pass  RED $fail  skipped $skipped"
if [[ $fail -eq 0 ]]; then
  echo "Rung 6 is measured. One undamaged medium and four damaged ones reached"
  echo "tc@box, each with exactly the ECC/PAR the host replay had named before"
  echo "any boot, and each transcript byte-identical to the clean boot apart"
  echo "from those counters -- with the executed handoff dumps identical too."
  echo "The three cases that must not boot did not: a codeword with two faults,"
  echo "mis-repaired and refused at the predicted CRC; three equal faults whose"
  echo "syndromes are all zero, refused with ECC=0; and a PXC1 medium, refused"
  echo "by container tag. See RECEIPT_BM602.md."
  echo "BM602_RUN_STATUS=GREEN"
else
  echo "BM602_RUN_STATUS=RED ($fail legs)"
fi
exit $((fail > 0))
