#!/usr/bin/env bash
# rung9/run_bm902_diff.sh — TASK_BM902 gate (stage2 constructs the handoff).
#
# Structure (mirrors run_oracle.sh discipline):
#   Phase A (construct): bm902_stage2_construct.py builds the full handoff
#     state OUR loader would hand the kernel — zeropage 4KB (from bzImage
#     bytes + loader-set fields per BM902_FIELD_PLAN.md), cmdline (oracle
#     string, byte-exact), register state. Runs TWICE (x2 determinism).
#   Phase B (differ): bm902_differ.py byte-compares constructed vs oracle:
#     L1 zeropage equal outside the field plan's whitelist union,
#     L2 cmdline byte-identical to oracle,
#     L3 registers match (rsp whitelisted),
#     L4 RED: flipped byte OUTSIDE whitelist -> differ exits non-zero
#        naming the offset,
#     L5 RED: mutant table (demote type_of_loader to MUST-MATCH) -> RED,
#     x2 construction runs byte-identical to each other.
#   Phase C (receipt): pins + PASS tail into bm902_diff_receipt.txt.
#
# Exit 0 = GATE PASS. Any missing RED = FAIL.
set -u
cd "$(dirname "$0")"
FAIL=0

# Phase B builds two inputs the differ then reads back by name, and Phase C pastes
# the two logs into the durable receipt. All four used to live at fixed /tmp names,
# so a concurrent run of this gate -- or bytes left behind by an aborted one --
# could be what a verdict, and the committed receipt, were computed over.
ZP_FLIP=$(mktemp "${TMPDIR:-/tmp}/bm902_zp_flipped.XXXXXX.bin") || { echo "GATE FAIL: mktemp"; exit 1; }
PLAN_MUT=$(mktemp "${TMPDIR:-/tmp}/BM902_FIELD_PLAN_mutant.XXXXXX.md") || { echo "GATE FAIL: mktemp"; exit 1; }
L4_LOG=$(mktemp "${TMPDIR:-/tmp}/bm902_l4.XXXXXX.log") || { echo "GATE FAIL: mktemp"; exit 1; }
L5_LOG=$(mktemp "${TMPDIR:-/tmp}/bm902_l5.XXXXXX.log") || { echo "GATE FAIL: mktemp"; exit 1; }
trap 'rm -f "$ZP_FLIP" "$PLAN_MUT" "$L4_LOG" "$L5_LOG"' EXIT

echo "=== BM902 DIFF GATE ==="

# ---------- Phase A: construct x2 ----------
for leg in 0 1; do
    python3 bm902_stage2_construct.py "bm902_zp_leg${leg}.bin" \
        "bm902_cmdline_leg${leg}.bin" "bm902_regs_leg${leg}.json" \
        || { echo "GATE FAIL: construct leg ${leg} errored"; exit 1; }
done
cp bm902_zp_leg0.bin bm902_zp.bin
cp bm902_cmdline_leg0.bin bm902_cmdline.bin
cp bm902_regs_leg0.json bm902_regs.json

# x2 determinism
if cmp -s bm902_zp_leg0.bin bm902_zp_leg1.bin && \
   cmp -s bm902_cmdline_leg0.bin bm902_cmdline_leg1.bin && \
   cmp -s bm902_regs_leg0.json bm902_regs_leg1.json; then
    echo "PHASE A PASS: x2 construction runs byte-identical"
else
    echo "GATE FAIL: construction legs differ (nondeterministic)"; exit 1
fi

# ---------- Phase B: differ legs ----------
echo "--- L1+L2+L3: differ (constructed vs oracle) ---"
python3 bm902_differ.py bm902_zp_leg0.bin bm902_cmdline_leg0.bin \
    bm902_regs_leg0.json BM902_FIELD_PLAN.md || FAIL=1
[ $FAIL -eq 0 ] || { echo "GATE FAIL: differ legs red"; exit 1; }

echo "--- L4 RED: flipped byte outside whitelist ---"
python3 - "$ZP_FLIP" <<'EOF' || { echo "GATE FAIL: flip setup errored"; exit 1; }
import sys
zp = bytearray(open('bm902_zp_leg0.bin', 'rb').read())
zp[0x214] ^= 0x01  # code32_start LSB — kernel-baked, MUST-MATCH, outside whitelist
open(sys.argv[1], 'wb').write(bytes(zp))
EOF
if python3 bm902_differ.py "$ZP_FLIP" bm902_cmdline_leg0.bin \
    bm902_regs_leg0.json BM902_FIELD_PLAN.md >"$L4_LOG" 2>&1; then
    echo "GATE FAIL: L4 differ PASSED on a corrupted zeropage (decoration)"; exit 1
fi
grep -q "0x214" "$L4_LOG" || { echo "GATE FAIL: L4 did not name the offset"; exit 1; }
echo "L4 PASS: differ RED on flipped byte, named offset 0x214:"
sed -n '1,5p' "$L4_LOG"

echo "--- L5 RED: mutant table demotes type_of_loader to MUST-MATCH ---"
python3 - "$PLAN_MUT" <<'EOF' || { echo "GATE FAIL: mutant table build errored"; exit 1; }
import sys
plan = open('BM902_FIELD_PLAN.md').read()
# mutate the whitelist fenced block: remove the 0x210 line
mut = plan.replace('0x210         type_of_loader\n', '')
assert mut != plan, 'mutant table: 0x210 line not found in fenced block'
open(sys.argv[1], 'w').write(mut)
EOF
if python3 bm902_differ.py bm902_zp_leg0.bin bm902_cmdline_leg0.bin \
    bm902_regs_leg0.json "$PLAN_MUT" >"$L5_LOG" 2>&1; then
    echo "GATE FAIL: L5 differ PASSED with type_of_loader demoted (whitelist decorative)"; exit 1
fi
grep -q "0x210" "$L5_LOG" || { echo "GATE FAIL: L5 did not name 0x210"; exit 1; }
echo "L5 PASS: mutant table -> differ RED naming 0x210:"
sed -n '1,5p' "$L5_LOG"

# ---------- Phase C: receipt ----------
{
    echo "# BM902 diff receipt"
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "oracle pins (unchanged):"
    sha256sum oracle_zp_leg0.bin oracle_zp_leg1.bin \
        oracle_cmdline_leg0.bin oracle_cmdline_leg1.bin
    echo "constructed pins:"
    sha256sum bm902_zp_leg0.bin bm902_zp_leg1.bin \
        bm902_cmdline_leg0.bin bm902_cmdline_leg1.bin
    echo "--- L4 RED tail ---"
    sed -n '1,8p' "$L4_LOG"
    echo "--- L5 RED tail ---"
    sed -n '1,8p' "$L5_LOG"
} > bm902_diff_receipt.txt

echo "--- artifact sha256 pins ---"
cat bm902_diff_receipt.txt
echo "GATE PASS: BM902 stage2 handoff (L1-L3 green, L4/L5 RED demonstrated, x2 identical)"
exit 0
