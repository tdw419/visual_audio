#!/usr/bin/env bash
# run_bm903_step1.sh — TASK_BM903 STEP 1 gate: the executed handoff.
#
# brief_bm903_e2e_pixel_boot.md method step 1: our own 16-bit stage2 must
# CONSTRUCT the BM902 protected-mode handoff, and the artifact it builds must
# byte-compare against BM902's host-constructed one, inside the frozen
# whitelist. Steps 2 (pixel medium) and 3 (end-to-end serial anchor) land in
# run_bm903_e2e.sh; this script closes step 1 only and says so.
#
# Standing hard rule carried from BM901 (ROADMAP Rung 9): a mismatch surfaces
# as a DIFF, never as a hang — every leg here runs under a wall-clock timeout.
set -uo pipefail
cd "$(dirname "$0")"

GDB_TIMEOUT=120        # per leg, inside bm903_capture.py too
BOOT_TIMEOUT=300       # whole capture (2 legs)
STEP_TIMEOUT=45        # any single build/differ step

pass=0; fail=0
ok()   { echo "  [PASS] $1"; pass=$((pass+1)); }
bad()  { echo "  [RED ] $1"; fail=$((fail+1)); }
hr()   { echo "----------------------------------------------------------------"; }

# S5 and S6 each build a zeropage that the differ then reads back by name, and the
# two legs demand OPPOSITE verdicts (RED expected, green expected), so whichever
# bytes sit at those names decide what is being adjudicated. They used to live at
# /tmp/bm903_zp_mutant.bin and /tmp/bm903_zp_white.bin, and at the time this changed
# both existed on disk, 4096 B each, stamped by an earlier BM-903 run.
ZP_MUTANT=$(mktemp "${TMPDIR:-/tmp}/bm903_zp_mutant.XXXXXX.bin") || { bad "mktemp ZP_MUTANT"; exit 1; }
ZP_WHITE=$(mktemp "${TMPDIR:-/tmp}/bm903_zp_white.XXXXXX.bin") || { bad "mktemp ZP_WHITE"; exit 1; }
trap 'rm -f "$ZP_MUTANT" "$ZP_WHITE"' EXIT

# ---------------------------------------------------------------- S0 pins
hr; echo "S0  input pins (nothing downstream is trusted past this line)"
declare -A PIN=(
  [vmlinuz64.extracted]=ee4545bb3eff57fabc1788aa5f776081dad200ea8019e1ef8a09a931a74db680
  [../rung7/core.gz]=7f1e370dd4e489fd76c99f76ed9ddd79fd7e51f23af457b07071b3898bb8b5a2
  [oracle_zp_leg0.bin]=c3120d8ef78f6a66a8fe09e5f1f6ba967f216e07a2fabbd9430a32daca051f16
  [oracle_cmdline_leg0.bin]=30cd829f2a88c80cb80bfef1d056c9d0d85683cc9e58dbd7b9e4c62ce03c43c3
  [bm902_zp.bin]=f6605707f28f97130fc6313e567993b0b012ea4bf7166be7fea4d46de9deadac
  [bm902_cmdline.bin]=30cd829f2a88c80cb80bfef1d056c9d0d85683cc9e58dbd7b9e4c62ce03c43c3
)
s0=1
for f in "${!PIN[@]}"; do
  got=$(sha256sum "$f" | cut -d' ' -f1)
  if [[ "$got" == "${PIN[$f]}" ]]; then ok "pin $f"
  else bad "pin $f: got ${got:0:16}… want ${PIN[$f]:0:16}…"; s0=0; fi
done
[[ $s0 -eq 1 ]] || { echo "S0 RED — aborting before any build"; exit 1; }

# ---------------------------------------------------------------- S1 build
hr; echo "S1  assemble stage2 + stage1, lay out the raw medium"
timeout $STEP_TIMEOUT python3 bm903_consts.py > bm903_step1_consts.log 2>&1 \
  && ok "bm903_consts.py" || { bad "bm903_consts.py"; tail -5 bm903_step1_consts.log; exit 1; }
timeout $STEP_TIMEOUT python3 bm903_mkimg.py > bm903_step1_mkimg.log 2>&1 \
  && ok "bm903_mkimg.py (nasm -f bin x2, medium written)" \
  || { bad "bm903_mkimg.py"; cat bm903_step1_mkimg.log; exit 1; }
grep -qi 'warning' bm903_step1_mkimg.log && { bad "nasm emitted a warning"; cat bm903_step1_mkimg.log; } \
  || ok "nasm clean (no warnings)"
MSECT=$(( $(stat -c%s bm903_medium.raw) / 512 ))
need=$(python3 -c "import json;print(json.load(open('bm903_layout.json'))['medium_sectors'])")
[[ "$MSECT" -eq "$need" ]] && ok "medium $MSECT sectors == layout" || bad "medium $MSECT != layout $need"

# ------------------------------------------------- S2 executed boot, capture
hr; echo "S2  boot the medium, stop on the kernel's first instruction, capture"
timeout $BOOT_TIMEOUT python3 bm903_capture.py > bm903_step1_capture.log 2>&1
rc=$?
tail -8 bm903_step1_capture.log
[[ $rc -eq 0 ]] && ok "capture rc=0 (both legs stopped at 0x100000 with HdrS at \$rsi)" \
  || bad "capture rc=$rc — timeout or no stop (a hang IS a failure, named: ${BOOT_TIMEOUT}s)"
for leg in 0 1; do
  grep -q 'BM903-S2 HANDOFF BUILT' bm903_serial_leg$leg.log \
    && ok "leg $leg serial shows stage2 EXECUTED through 'HANDOFF BUILT'" \
    || bad "leg $leg serial lacks the stage2 checkpoint — did code run at all?"
  sed -n '1,10p' bm903_serial_leg$leg.log | sed 's/^/      /'
done

# ---------------------------------------------------------------- S3 differ
hr; echo "S3  executed-vs-constructed differential (L1/L2/L2b/L3)"
for leg in 0 1; do
  timeout $STEP_TIMEOUT python3 bm903_differ.py \
      bm903_zp_leg$leg.bin bm903_cmdline_leg$leg.bin bm903_regs_leg$leg.json \
      > bm903_step1_differ_leg$leg.log 2>&1
  rc=$?
  sed 's/^/      /' bm903_step1_differ_leg$leg.log
  [[ $rc -eq 0 ]] && ok "leg $leg differ green" || bad "leg $leg differ rc=$rc"
done

# ------------------------------------------------------------ S4 determinism
hr; echo "S4  two independent boots agree byte-for-byte"
for pair in bm903_zp_leg0.bin:bm903_zp_leg1.bin \
            bm903_cmdline_leg0.bin:bm903_cmdline_leg1.bin \
            bm903_regs_leg0.json:bm903_regs_leg1.json; do
  a=${pair%%:*}; b=${pair##*:}
  cmp -s "$a" "$b" && ok "$a == $b" || bad "$a != $b (non-deterministic capture)"
done

# --------------------------------------------------- S5 RED: single byte (L5)
hr; echo "S5  RED leg — flip one zeropage byte OUTSIDE the whitelist"
# 0x244 version_string: MUST-MATCH class, kernel-baked, not whitelisted.
python3 - "$ZP_MUTANT" <<'PY'
import sys
from pathlib import Path
b = bytearray(Path('bm903_zp_leg0.bin').read_bytes())
OFF = 0x244
assert b[OFF] == 0, f'fixture byte at {OFF:#x} is not 0 — pick another offset'
b[OFF] ^= 0x01
Path(sys.argv[1]).write_bytes(bytes(b))
print(f'  mutant: 0x244 0x00 -> 0x01 (outside every whitelist row)')
PY
timeout $STEP_TIMEOUT python3 bm903_differ.py "$ZP_MUTANT" \
    bm903_cmdline_leg0.bin bm903_regs_leg0.json --expect-fail \
    > bm903_step1_red.log 2>&1
rc=$?
sed 's/^/      /' bm903_step1_red.log
[[ $rc -eq 0 ]] && ok "mutant caught: differ exits non-zero naming 0x244" \
  || bad "mutant NOT caught — the differ is decoration (brief: gate fails the row)"

# ------------------------------------------------- S6 control: whitelist byte
hr; echo "S6  control — a byte INSIDE the whitelist must NOT be flagged"
python3 - "$ZP_WHITE" <<'PY'
import sys
from pathlib import Path
b = bytearray(Path('bm903_zp_leg0.bin').read_bytes())
b[0x210] ^= 0x01          # type_of_loader: whitelisted row
Path(sys.argv[1]).write_bytes(bytes(b))
PY
timeout $STEP_TIMEOUT python3 bm903_differ.py "$ZP_WHITE" \
    bm903_cmdline_leg0.bin bm903_regs_leg0.json > bm903_step1_ctrl.log 2>&1
rc=$?
grep -E '^L1' bm903_step1_ctrl.log | sed 's/^/      /'
[[ $rc -eq 0 ]] && ok "whitelisted change still green (S5's failure is specificity, not noise)" \
  || bad "whitelisted change went RED — the whitelist is not being honoured"

hr
echo "STEP 1 TALLY: $pass pass, $fail red"
if [[ $fail -eq 0 ]]; then
  echo "BM903 STEP 1 GREEN: our executed stage2 constructs the BM902 handoff"
  echo "(diff: 4 bytes, all the constructed initrd pair, all whitelisted)."
  echo "This gate closes STEP 1 ONLY: the pixel medium and the serial anchor are"
  echo "run_bm903_e2e.sh's legs, not this script's — see RECEIPT_BM903_E2E.md."
  exit 0
fi
echo "BM903 STEP 1 RED — see the legs above"
exit 1
