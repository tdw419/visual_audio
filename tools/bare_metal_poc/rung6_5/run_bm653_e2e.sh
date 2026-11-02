#!/usr/bin/env bash
# run_bm653_e2e.sh -- Rung 6.5, option C (BM652's measurement, BM651's image):
# run an executable OUT OF THE SELF-REPAIRING MEDIUM, in the space the medium
# already wasted.
#
# What has to be true before a single boot counts:
#   * the medium is rung 6's medium -- same payload length, same 7 planes, same
#     46,609 sectors -- with the image sitting in a padding group, checked by
#     scanning the delta against the landed payload rather than asserting it;
#   * every number the boots will be judged against -- ECC/PAR counters, the CRC
#     the gate will compute, the NID the image must echo, the 256 wrong bytes of
#     the corrector-off control, the 2 surviving bytes of the scribbler's poison
#     -- is in bm653_fixtures.json BEFORE this script boots anything, and comes
#     out of bm653_mkimg.py's own host replay of the medium it just wrote.
#
# Nothing in this file contains an expected number. It asks; the fixture file
# answers. A leg that gets a LOADER line wrong is not retried -- bm653_gate.py
# refuses to re-roll a deterministic die. Anchor legs get $BOOT_ATTEMPTS boots
# because Tiny Core's autologin race is measured (BM903: 3/8 and 5/8), not
# because the loader is flaky.
#
# Two consecutive clean passes are required ($PASSES); each pass re-runs the
# static stages, so a prediction that only held because a stale .inc was on
# disk fails here rather than in the receipt.
#
# Run: bash rung6_5/run_bm653_e2e.sh          (both passes: 334 s and 566 s
#                                              measured; the gap is 1 vs 7
#                                              autologin re-boots, not the loader)
#      bash rung6_5/run_bm653_e2e.sh --resume (skip stages this run already made
#                                              GREEN; reads the recorded EXIT
#                                              CODE, never the word GREEN)
set -u
cd "$(dirname "$0")"
OUT=logs
mkdir -p "$OUT"
RE=${1:-}
PASSES=${PASSES:-2}
BOOT_ATTEMPTS=8
ATTEMPT_TIMEOUT=45
LEGS="exec_green exec_image_repaired exec_beeoff_control exec_two_symbol_in_image \
      exec_blind_spot_in_image exec_halt exec_scribbler"

run_stage() {                          # run_stage <status stem> <cmd...>
  local stem=$1; shift
  if was_green "$stem"; then
    echo "  [SKIP] $stem -- rc=0 recorded by this run (--resume)"; return 0
  fi
  local t0=$(date +%s) rc
  "$@" > "$OUT/$stem.log" 2>&1; rc=$?
  echo "  [$( [[ $rc -eq 0 ]] && echo PASS || echo 'RED ')] $stem  rc=$rc  $(( $(date +%s) - t0 ))s"
  echo "$stem rc=$rc $(tail -1 "$OUT/$stem.log")" > "$OUT/$stem.status"
  [[ $rc -eq 0 ]] || sed 's/^/        /' "$OUT/$stem.log" | tail -25
  return $rc
}

was_green() {                          # was_green <status stem>
  [[ "$RE" == "--resume" && -f "$OUT/$1.status" ]] && grep -q " rc=0 " "$OUT/$1.status"
}

run_leg() {                            # run_leg <pass> <fixture>
  local stem=p$1_$2
  if was_green "$stem"; then
    echo "  [SKIP] $2 already GREEN on this run (--resume)"; return 0
  fi
  local t0=$(date +%s) rc
  python3 bm653_gate.py "$2" --attempts $BOOT_ATTEMPTS --budget $ATTEMPT_TIMEOUT \
      > "$OUT/$stem.log" 2>&1; rc=$?
  echo "  [$( [[ $rc -eq 0 ]] && echo PASS || echo 'RED ')] boot $2  rc=$rc  $(( $(date +%s) - t0 ))s  $(grep -m1 "^$2:" "$OUT/$stem.log")"
  echo "$stem rc=$rc $(grep -m1 "^$2:" "$OUT/$stem.log" || echo 'no verdict line')" > "$OUT/$stem.status"
  [[ $rc -eq 0 ]] || sed 's/^/        /' "$OUT/$stem.log" | tail -25
  return $rc
}

one_pass() {                           # one_pass <pass number>  -> 0 if clean
  local P=$1 fail=0 stem=p$1

  echo "----------------------------------------------------------------"
  echo "STATIC 1/5  codec: rung 6's medium + one padding group turned into a target"
  run_stage ${stem}_s1_codec python3 bm653_pxcodec.py || fail=$((fail+1))
  echo "        $(tail -1 "$OUT/${stem}_s1_codec.log")"

  echo "STATIC 2/5  loader fork: named deltas onto rung6's own text"
  run_stage ${stem}_s2_construct python3 bm653_construct.py || fail=$((fail+1))
  echo "        $(grep -m1 '^stage2:' "$OUT/${stem}_s2_construct.log")"

  echo "STATIC 3/5  images: BM651's four variants rebuilt to its landed evidence, + the scribbler"
  run_stage ${stem}_s3_img2 python3 bm653_img2.py || fail=$((fail+1))
  echo "        $(tail -1 "$OUT/${stem}_s3_img2.log")"

  echo "STATIC 4/5  media + PREDICTIONS: 7 fixtures, each with its host replay before any boot"
  run_stage ${stem}_s4_mkimg python3 bm653_mkimg.py || fail=$((fail+1))
  echo "        $(tail -1 "$OUT/${stem}_s4_mkimg.log")"
  # The predictions file is the thing the boots are judged against. If a static
  # stage rewrote it after a previous pass, say so with its age, not with hope.
  echo "        bm653_fixtures.json: $(stat -c '%y' bm653_fixtures.json | cut -d. -f1)"

  echo "STATIC 5/5  size: the leg's code cost, measured on the fork that shipped"
  # Needs build/*.asm, which mkimg writes -- so it runs after stage 4, not with
  # the other text stages. nasm only: no boots, no media.
  run_stage ${stem}_s5_size python3 bm653_size.py || fail=$((fail+1))
  echo "        $(head -2 "$OUT/${stem}_s5_size.log" | tail -1)"
  echo "        $(grep -m1 '^control' "$OUT/${stem}_s5_size.log")"

  echo "----------------------------------------------------------------"
  echo "PREFLIGHT: the pinned BM903 handoffs the identity stage compares against"
  # This row's reference is a PINNED COPY under evidence/refs/, not rung9's
  # working file: `rung9/run_bm903_e2e.sh` writes bm903_px_*_leg0 at its capture
  # legs, so the original can move underneath a later run -- and a clean
  # checkout has none at all. Asking here costs a second; asking after seven
  # boots costs a pass (measured 2026-09-20).
  run_stage ${stem}_refs python3 bm653_refs.py --check || fail=$((fail+1))
  echo "        $(tail -1 "$OUT/${stem}_refs.log")"

  # Snapshot the predictions with the one measured-duration line removed, BEFORE
  # any boot of this pass, so the next pass can be asked whether it derives the
  # same ones from a clean rebuild.
  grep -v '"host_replay_seconds"' bm653_fixtures.json > "$OUT/${stem}_fixtures_noclock.json"

  echo "----------------------------------------------------------------"
  echo "BOOTS 1-3: the two that must reach tc@box, then the corrector-off control"
  for f in exec_green exec_image_repaired exec_beeoff_control; do
    run_leg "$P" "$f" || fail=$((fail+1))
  done
  echo "BOOTS 4-7: two more refusals, the hung image, and the scribbler"
  for f in exec_two_symbol_in_image exec_blind_spot_in_image exec_halt exec_scribbler; do
    run_leg "$P" "$f" || fail=$((fail+1))
  done

  echo "----------------------------------------------------------------"
  echo "IDENTITY: transcripts against the clean boot + the executed handoff dumps"
  if was_green ${stem}_identity; then
    echo "  [SKIP] identity already GREEN on this run (--resume)"
  else
    local t0=$(date +%s) rc
    python3 bm653_identity.py > "$OUT/${stem}_identity.log" 2>&1; rc=$?
    echo "  [$( [[ $rc -eq 0 ]] && echo PASS || echo 'RED ')] identity  rc=$rc  $(( $(date +%s) - t0 ))s  $(grep -m1 '^IDENTITY:' "$OUT/${stem}_identity.log")"
    echo "identity rc=$rc $(grep -m1 '^IDENTITY:' "$OUT/${stem}_identity.log" || echo 'no summary line')" \
      > "$OUT/${stem}_identity.status"
    [[ $rc -eq 0 ]] || sed -n '/^  \[RED \]/p' "$OUT/${stem}_identity.log" | sed 's/^/        /'
    fail=$((fail + rc))
  fi

  echo "----------------------------------------------------------------"
  echo "REGRESSION: the un-forked rung-6 loader still boots its own medium"
  # Option C lives in a FORK of bm602_stage2_px.asm and a PATCH of the payload,
  # so rung 6's own row has to stay green beside it: the clean PXC2-E medium,
  # the original loader, the original gate. rung6/ writes only ignored paths.
  if was_green ${stem}_r6_clean; then
    echo "  [SKIP] BM602 clean leg already GREEN on this run (--resume)"
  else
    local t0=$(date +%s) rc
    ( cd ../rung6 && python3 bm602_gate.py clean --attempts $BOOT_ATTEMPTS \
        --budget $ATTEMPT_TIMEOUT ) > "$OUT/${stem}_r6_clean.log" 2>&1; rc=$?
    echo "  [$( [[ $rc -eq 0 ]] && echo PASS || echo 'RED ')] bm602 clean  rc=$rc  $(( $(date +%s) - t0 ))s"
    echo "bm602 clean rc=$rc $(grep -m1 '^clean:' "$OUT/${stem}_r6_clean.log" || echo 'no verdict line')" \
      > "$OUT/${stem}_r6_clean.status"
    [[ $rc -eq 0 ]] || tail -20 "$OUT/${stem}_r6_clean.log" | sed 's/^/        /'
    fail=$((fail + (rc > 0)))
  fi

  return $((fail > 0))
}

T0=$(date +%s)
green_passes=0
for P in $(seq 1 $PASSES); do
  case $P in 1) L=A;; 2) L=B;; *) L=P$P;; esac
  echo "================================================================"
  echo "PASS $P of $PASSES   (BM653 needs $PASSES consecutive clean passes)"
  echo "================================================================"
  one_pass "$P" 2>&1 | tee "$OUT/pass$P.out"
  rc=${PIPESTATUS[0]}

  # The row's own reproducibility claim, measured rather than asserted: pass 2
  # rebuilds every artifact from source and must DERIVE THE SAME PREDICTIONS
  # that its own boots were then judged against. Only the clock line may differ.
  if [[ $P -gt 1 && -f "$OUT/p$((P - 1))_fixtures_noclock.json" ]]; then
    if cmp -s "$OUT/p$((P - 1))_fixtures_noclock.json" "$OUT/p${P}_fixtures_noclock.json"; then
      echo "PASS $P: predictions re-derived from a clean rebuild are byte-identical" \
           "to pass $((P - 1))'s, apart from the replay-duration line"
    else
      echo "PASS $P: [RED] a clean rebuild produced DIFFERENT predictions --" \
           "the fixtures file is not a function of the sources"
      diff "$OUT/p$((P - 1))_fixtures_noclock.json" "$OUT/p${P}_fixtures_noclock.json" | head -10
      rc=1
    fi
  fi

  if [[ $rc -eq 0 ]]; then
    green_passes=$((green_passes + 1))
    echo "PASS $P: clean"
  else
    # "Two consecutive clean passes" means a red pass RESETS the count -- the
    # second pass of a 1-green-1-red pair proves nothing about the first.
    green_passes=0
    echo "PASS $P: NOT clean -- stopping; nothing after a red pass is consecutive"
    break
  fi
done

echo "================================================================"
echo "$green_passes of $PASSES passes clean, $(($(date +%s) - T0)) s wall"
if [[ $green_passes -eq $PASSES ]]; then
  # Land the evidence a reader can check without re-running anything: the
  # predictions as derived, the seven wires, the handoff dumps, and the two
  # pass summaries. Generated by this run, not typed up afterwards.
  D=evidence/bm653
  mkdir -p "$D/transcripts" "$D/dumps"
  cp -f "$OUT/p${PASSES}_fixtures_noclock.json" "$D/fixtures_predictions.json"
  cp -f bm653_stage2_px.asm "$D/bm653_stage2_px.asm"   # the loader text that ran
  for f in $LEGS; do cp -f "logs/$f.serial" "$D/transcripts/$f.serial"; done
  cp -f "$OUT/p${PASSES}_s5_size.log" "$D/size.txt"
  for Q in $(seq 1 $PASSES); do
    [[ -f "$OUT/pass$Q.out" ]] || continue
    grep -E '^  \[(PASS|RED |SKIP)\]|^STATIC|^BOOTS|^IDENTITY|^REGRESSION' \
      "$OUT/pass$Q.out" > "$D/e2e_pass_$Q.txt"
  done
  if ls captures/bm653_px_*_leg0.bin >/dev/null 2>&1; then
    cp -f captures/bm653_px_exec_*_leg*.bin captures/bm653_px_exec_*_leg*.json "$D/dumps/"
    echo "dumps landed: $(ls "$D/dumps" | wc -l) files"
  else
    echo "no captures on disk -- identity was skipped, so there are no dumps to land"
  fi
  echo "evidence: $D ($(ls "$D" | wc -l) entries, plus transcripts/ and dumps/)"
  echo "BM653_RUN_STATUS=GREEN"
  exit 0
fi
echo "BM653_RUN_STATUS=RED"
exit 1
