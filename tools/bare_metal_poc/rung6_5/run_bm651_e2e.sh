#!/bin/bash
# RUNG6.5 / BM-651 gate: EXEC-FROM-DATA. The second pixel image, once the
# rung-5 CRC gate has accepted it, is executed -- and the loader then checks
# the image kept its side of a contract (a mailbox word + an echoed 16-bit
# identity) before it prints EXEC=OK.
#
# Fork discipline: rung5/ is read-only. bm651_construct.py turns it into
# bm651_stage2.asm by NAMED deltas that round-trip, so every byte outside the
# new leg is the byte rung 5 measured -- which is what lets WRITE=OK / IMG2
# CRC / STAGE2 CKSUM still mean "rung 5 works" here instead of "we hope the
# fork did not break it".
#
# Legs: green x2 (reboot, no re-encode), then three ways the image can break
# its contract (each built as its own image, so each fails exactly ONE loader
# check and still passes the other), then a hung image, then a corrupted
# medium that must never be entered, then a re-green from the untouched PNG.
#
# Run: bash rung6_5/run_bm651_e2e.sh
# Background mode for a tool caller: ~8 boots x $TMO + 4 builds exceeds the
# 120 s default; the wall clock of a full run is printed at the end.
set -u -o pipefail
cd "$(dirname "$0")"
T0=$(date +%s)

TMO=20
SCALE=65536
VARS="green noecho nombox halt"
fail() { echo "GATE651 FAIL: $1"; exit 1; }
fx() { grep -m1 "^$1=" bm651_fixtures.txt | cut -d= -f2-; }

# Leg [2] compares the medium's hashes before and after the second boot, and the
# compare IS the verdict. The two hash files used to live at the fixed names
# /tmp/bm651_h1.txt and _h2.txt, so a leftover or a concurrent run's h1 could
# satisfy it with bytes this run never hashed.
H1_TXT=$(mktemp "${TMPDIR:-/tmp}/bm651_h1.XXXXXX") || fail "mktemp"
H2_TXT=$(mktemp "${TMPDIR:-/tmp}/bm651_h2.XXXXXX") || fail "mktemp"
trap 'rm -f "$H1_TXT" "$H2_TXT"' EXIT

clean() { tr -d '\r' < "$1" | grep -v '^$' > "$2"; }   # $2 is the receipt text

boot() {                       # $1 medium, $2 serial log; rc is 124 by design
    local MED=$1 LOG=$2
    timeout $TMO qemu-system-x86_64 -drive file=$MED,format=raw,if=ide \
        -display none -no-reboot -serial file:$LOG 2>/dev/null
    return $?
}

build_variant() {              # $1 variant: consts -> stage2 -> pad -> stage1 -> medium
    local V=$1 DEFS
    DEFS=$(python3 bm651_consts.py $SCALE img2_$V.bin) || return 1
    echo "$DEFS" > defs_$V.txt
    nasm -f bin bm651_stage2.asm $DEFS -l stage2_$V.lst -o stage2_code_$V.bin || return 1
    python3 ../rung5/rung4_pad.py $SCALE stage2_code_$V.bin stage2_$V.bin || return 1
    python3 ../rung5/rung4_consts.py stage2_$V.bin >/dev/null || return 1
    nasm -f bin ../rung5/stage1.asm -I . -o stage1_$V.bin || return 1
    [ "$(stat -c%s stage1_$V.bin)" -eq 512 ] || return 1
    python3 ../rung5/rung5_codec.py encode stage1_$V.bin stage2_$V.bin img2_$V.bin \
        bm651_$V.png bm651_$V.raw bm651_$V.json >/dev/null || return 1
}

mkdir -p evidence

# ==================== [0] build + pre-boot predictions ====================
echo "=== [0] provenance: delta fork, image variants, four media, host roundtrip ==="
# rung5's layout script writes rung5_layout.inc INTO THE CWD -- and its
# build-time region-disjointness gate is the thing that refuses a write target
# that would overlap the image or the planes (rung-5 trap 10). Called here, not
# assumed present: a clean checkout has no .inc.
python3 ../rung5/rung5_layout.py $SCALE > /dev/null || fail "layout disjointness"
python3 bm651_construct.py > evidence/construct_deltas.txt || fail "construct"
cat evidence/construct_deltas.txt
python3 bm651_img2.py > evidence/img2_variants.txt || fail "img2 variants"
cat evidence/img2_variants.txt

# Matched baseline: rung5's own stage2.asm assembled with the SAME defines the
# fork got, minus the one define this rung adds. So the size difference is the
# leg, not a different scale or a different image. (After the builds: it reads
# defs_green.txt, which the build writes.)
for V in $VARS; do
    build_variant $V || fail "build $V"
done
BASEDEFS=$(sed 's/ -DEXPECTED_EXEC_NID=0x[0-9A-F]*//' defs_green.txt)
nasm -f bin ../rung5/stage2.asm $BASEDEFS -o stage2_rung5_baseline.bin \
    || fail "rung5 baseline assemble"
echo "rung5 baseline code: $(stat -c%s stage2_rung5_baseline.bin) B"
BASE=$(stat -c%s stage2_rung5_baseline.bin)
for V in $VARS; do
    C=$(stat -c%s stage2_code_$V.bin)
    echo "  $V: code $C B, leg $((C - BASE)) B over the rung5 baseline; medium $(stat -c%s bm651_$V.raw) B"
done > evidence/build_sizes.txt || fail "variant build"
cat evidence/build_sizes.txt

# predictions, written BEFORE any qemu runs: the legs grep against this file.
: > bm651_fixtures.txt
for V in $VARS; do
    {
    echo "${V}_nid=$(sed -n 's/.*-DEXPECTED_EXEC_NID=0x\([0-9A-F]*\).*/\1/p' defs_$V.txt)"
    echo "${V}_img2crc=$(python3 -c "import json;print(json.load(open('bm651_$V.json'))['img2_crc32'])")"
    echo "${V}_s2crc=$(python3 -c "import json;print(json.load(open('bm651_$V.json'))['payload_crc32'])")"
    echo "${V}_stage2code=$(stat -c%s stage2_code_$V.bin)"
    } >> bm651_fixtures.txt
done
echo "img2_base=$(python3 -c "import json;print(json.load(open('bm651_green.json'))['img2_base'])")" >> bm651_fixtures.txt
grep -oP 'WR_LBA\s+equ \K[0-9]+' rung5_layout.inc | sed 's/^/wr_lba=/' >> bm651_fixtures.txt
for V in $VARS; do
    [ -n "$(fx ${V}_nid)" ] && [ -n "$(fx ${V}_img2crc)" ] || fail "fixtures incomplete for $V"
done
cat bm651_fixtures.txt | tee evidence/fixtures_before_boot.txt

# host-side roundtrip on the green medium (independent of the guest's CRC)
python3 ../rung5/rung5_codec.py decode bm651_green.raw bm651_green.json \
    > evidence/host_decode_green.txt || fail "host decode"
grep -q "stage2 crc32=$(fx green_s2crc)" evidence/host_decode_green.txt \
    || fail "host decode stage2 CRC disagrees with meta"
grep -q "img2 crc32=$(fx green_img2crc)" evidence/host_decode_green.txt \
    || fail "host decode img2 CRC disagrees with meta"

# Who is allowed to print the banner? If the loader's own bytes contained the
# string, `IMG2EXEC BANNER NID=...` on the wire would prove nothing about the
# image -- it would only prove stage2 ran. So: exactly once in the image,
# nowhere in any variant's stage2 payload (padded, so the filler is covered
# too) or in stage1. This is the claim's load-bearing host-side half.
python3 - > evidence/banner_provenance.txt <<'EOF' || fail "banner provenance"
import glob
sig = b'IMG2EXEC BANNER NID='
for v in ('green', 'noecho', 'nombox', 'halt'):
    img = open(f'img2_{v}.bin', 'rb').read()
    assert img.count(sig) == 1, f'{v}: banner string in its image {img.count(sig)} times'
    pay = open(f'stage2_{v}.bin', 'rb').read()
    s1 = open(f'stage1_{v}.bin', 'rb').read()
    assert sig not in s1, f'{v}: stage1 carries the banner string'
    assert sig not in pay, f'{v}: stage2 payload carries the banner string'
    print(f'{v}: banner string in the image only '
          f'(img2 1x, stage2 {len(pay)} B 0x, stage1 {len(s1)} B 0x)')
print('=> the transcript line can only have come from the executed pixels')
EOF
cat evidence/banner_provenance.txt

G_NID=$(fx green_nid);      G_CRC=$(fx green_img2crc)
NE_NID=$(fx noecho_nid);    NE_CRC=$(fx noecho_img2crc)
NM_NID=$(fx nombox_nid);    NM_CRC=$(fx nombox_img2crc)
H_NID=$(fx halt_nid)

require() {                   # $1 log, $2..: must-be-present patterns
    local L=$1; shift
    while [ $# -gt 0 ]; do
        grep -q "$1" $L || fail "$2 GOT: $(tr -d '\r\n' < $L | tail -c 200)"
        shift 2
    done
}
forbid() {                    # $1 log, $2..: must-be-absent patterns
    local L=$1; shift
    while [ $# -gt 0 ]; do
        grep -q "$1" $L && fail "$2 (forbidden pattern '$1' present)"
        shift 2
    done
}

echo "=== [1] GREEN-A: pixels executed, contract kept, EXEC=OK ==="
boot bm651_green.raw serial_gA.log
clean serial_gA.log serial_gA_clean.log
cat serial_gA_clean.log
require serial_gA_clean.log \
    "PXC1-RUNG5"                         "no hello" \
    "IMG2 CRC=$G_CRC"                    "BM-501 read leg broken by the fork" \
    "WRITE=OK"                           "BM-502 write leg broken by the fork" \
    "STAGE2 CKSUM=[0-9A-F]* EXEC"        "no stage2 self receipt" \
    "IMG2EXEC BANNER NID=$G_NID"         "the image never printed its banner" \
    "EXEC=OK"                            "no EXEC=OK verdict"
forbid serial_gA_clean.log "EXEC=BAD-MAILBOX" "green hit a refusal" \
                               "EXEC=NO-BANNER" "green hit a refusal"
# the banner must come AFTER the write and the receipt: the leg's ordering is
# the safety property (a corrupt image is never reached, the copy-down never
# eats the bounce buffer), and the transcript line order is the witness.
BORDER=$(grep -n "IMG2EXEC BANNER" serial_gA_clean.log | cut -d: -f1)
WORDER=$(grep -n "WRITE=OK"       serial_gA_clean.log | cut -d: -f1)
RORDER=$(grep -n "STAGE2 CKSUM"   serial_gA_clean.log | cut -d: -f1)
[ "$WORDER" -lt "$RORDER" ] && [ "$RORDER" -lt "$BORDER" ] \
    || fail "leg ordering wrong: WRITE=$WORDER receipt=$RORDER banner=$BORDER"

echo "=== [2] GREEN-B: reboot the SAME medium, no re-encode; pixels unchanged ==="
python3 - bm651_green.raw $(fx img2_base) $(fx wr_lba) > "$H1_TXT" <<'EOF'
import sys, hashlib
med, base, wr = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) * 512
b = open(med, 'rb').read()
print('img2_sha=%064x' % int(hashlib.sha256(b[base:base+2048]).hexdigest(), 16))
print('marker_sha=%064x' % int(hashlib.sha256(b[wr:wr+2048]).hexdigest(), 16))
EOF
boot bm651_green.raw serial_gB.log
clean serial_gB.log serial_gB_clean.log
diff serial_gA_clean.log serial_gB_clean.log > /dev/null \
    || fail "GREEN-B transcript differs from GREEN-A: $(diff serial_gA_clean.log serial_gB_clean.log | head)"
require serial_gB_clean.log "EXEC=OK" "second boot did not execute"
python3 - bm651_green.raw $(fx img2_base) $(fx wr_lba) > "$H2_TXT" <<'EOF'
import sys, hashlib
med, base, wr = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) * 512
b = open(med, 'rb').read()
print('img2_sha=%064x' % int(hashlib.sha256(b[base:base+2048]).hexdigest(), 16))
print('marker_sha=%064x' % int(hashlib.sha256(b[wr:wr+2048]).hexdigest(), 16))
EOF
cmp "$H1_TXT" "$H2_TXT" || fail "executing the image perturbed the medium"
cp "$H2_TXT" evidence/medium_hashes_after_boot2.txt
echo "GREEN-B: identical transcript; the executed image's bytes and the written marker are byte-identical across the reboot"

echo "=== [3] RED-A: image that runs but never echoes its identity -> EXEC=NO-BANNER ==="
boot bm651_noecho.raw serial_ra.log
clean serial_ra.log serial_ra_clean.log
cat serial_ra_clean.log
require serial_ra_clean.log \
    "IMG2 CRC=$NE_CRC"            "noecho variant: img2 CRC gate should still pass" \
    "IMG2EXEC BANNER NID=$NE_NID" "noecho: the image did not run" \
    "EXEC=NO-BANNER 0000 EXP=$NE_NID" "noecho: the NID check did not refuse"
forbid serial_ra_clean.log "EXEC=OK" "noecho: refusal did not stop the verdict"
# independence: this image DID keep the mailbox contract, so the mailbox
# check must not have fired -- the two loader checks are separate legs.
forbid serial_ra_clean.log "EXEC=BAD-MAILBOX" "noecho: mailbox check fired too (checks not independent)"

echo "=== [4] RED-B: image that keeps the mailbox but not the echo -> EXEC=BAD-MAILBOX ==="
boot bm651_nombox.raw serial_rb.log
clean serial_rb.log serial_rb_clean.log
cat serial_rb_clean.log
require serial_rb_clean.log \
    "IMG2 CRC=$NM_CRC"            "nombox variant: img2 CRC gate should still pass" \
    "IMG2EXEC BANNER NID=$NM_NID" "nombox: the image did not run" \
    "EXEC=BAD-MAILBOX 0000 EXP=4B4F" "nombox: the mailbox check did not refuse"
forbid serial_rb_clean.log "EXEC=OK" "nombox: refusal did not stop the verdict"
forbid serial_rb_clean.log "EXEC=NO-BANNER" "nombox: NID check fired too (checks not independent)"

echo "=== [5] HANG: image that never returns -- only the host can call it ==="
boot bm651_halt.raw serial_h.log
clean serial_h.log serial_h_clean.log
cat serial_h_clean.log
require serial_h_clean.log \
    "PXC1-RUNG5"                     "hang: no hello" \
    "WRITE=OK"                       "hang: write leg did not run" \
    "STAGE2 CKSUM=[0-9A-F]* EXEC"    "hang: no self receipt, so the handover was never reached" \
    "IMG2EXEC BANNER NID=$H_NID"     "hang: never entered the image"
# DEFECT-R651-1 (measured 2026-09-20 run 2): this leg first tried to diff the
# hang transcript against green "up to the handover". That can never pass --
# each variant embeds its own image CRC, sum16, CKSUM and NID, so lines 2..6
# differ by construction. The comparable thing is STRUCTURE: the banner is the
# last line the loader ever emitted, and the line count is green's minus the
# verdict green got.
[ "$(tail -n 1 serial_h_clean.log)" = "IMG2EXEC BANNER NID=$H_NID" ] \
    || fail "hang: something followed the handover: $(tail -n 1 serial_h_clean.log)"
HN=$(wc -l < serial_h_clean.log); GN=$(wc -l < serial_gA_clean.log)
[ "$HN" -eq $(($GN - 1)) ] || fail "hang leg is $HN lines, green is $GN: not 'green minus the verdict'"
forbid serial_h_clean.log "EXEC=OK" "hang: a verdict appeared after a hung image"
forbid serial_h_clean.log "EXEC=BAD-MAILBOX" "hang: refused without a return" \
                               "EXEC=NO-BANNER" "hang: refused without a return"
echo "hang leg: entered, receipt printed, banner last -- and NO verdict in ${TMO}s. rc=124 is every leg's end state (the loader halts forever), so this is a host-side absence claim, not a guest watchdog: nothing inside this design can time out its own image."

echo "=== [6] RED-CRC: corrupt the image's pixels -> the CRC gate refuses BEFORE execution ==="
IMG2_BASE=$(fx img2_base)
OFF=$IMG2_BASE
ORIG=$(python3 -c "print(open('bm651_green.raw','rb').read()[$OFF])")
NEW=$((ORIG ^ 255))
qemu-io -c "write -P $NEW $OFF 1" bm651_green.raw >/dev/null 2>&1 || fail "qemu-io corrupt"
[ "$(python3 -c "print(open('bm651_green.raw','rb').read()[$OFF])")" -eq "$NEW" ] \
    || fail "corruption did not land"
NEWCRC=$(python3 - "$OFF" "$ORIG" "$IMG2_BASE" <<'EOF'
import json, sys, zlib
off, orig, base = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
plane_len = json.load(open('bm651_green.json'))['img2_len'] // 4
rel = off - base
idx = (rel % plane_len) * 4 + (rel // plane_len)
img = bytearray(open('img2_green.bin', 'rb').read())
assert img[idx] == orig, f'host map: img2[{idx}]={img[idx]} != medium byte {orig}'
img[idx] ^= 255
print('%08X' % (zlib.crc32(bytes(img)) & 0xFFFFFFFF))
EOF
) || fail "host crc arithmetic"
boot bm651_green.raw serial_rc.log
clean serial_rc.log serial_rc_clean.log
cat serial_rc_clean.log
require serial_rc_clean.log \
    "IMG2 FAIL CRC=$NEWCRC EXP=$G_CRC" "RED-CRC: no specified refusal (got the transcript above)"
# the claim under test, in its strongest form: an image that fails the CRC is
# never entered, so the banner -- which only the image can print -- must be
# absent, and so must any EXEC verdict.
forbid serial_rc_clean.log "IMG2EXEC BANNER" "RED-CRC: a corrupt image was EXECUTED" \
                               "EXEC=" "RED-CRC: an exec verdict after refusal" \
                               "WRITE=" "RED-CRC: the write leg ran past refusal (rung-5 invariant)"

echo "=== [7] RE-GREEN: rebuild the medium from the untouched PNG, boot, identical ==="
python3 ../rung5/rung5_codec.py bake bm651_green.png bm651_green.raw bm651_green.json \
    >/dev/null || fail "rebake"
boot bm651_green.raw serial_rg.log
clean serial_rg.log serial_rg_clean.log
diff serial_gA_clean.log serial_rg_clean.log > /dev/null \
    || fail "RE-GREEN transcript differs from GREEN-A"
echo "RE-GREEN: pristine pixels from the archive PNG boot identically after a corrupted medium"

echo
echo "=== GATE651 PASS ($(($(date +%s) - T0)) s wall, $(wc -l < bm651_fixtures.txt) predictions fixed before the first boot, 7 boots) ==="
for f in gA gB ra rb h rc rg; do
    echo "serial_$f: $(tr -d '\n' < serial_${f}_clean.log | tail -c 96)"
done
# *.log is gitignored in this tree, so the receipts are kept as .serial text.
mkdir -p evidence/transcripts
for f in gA gB ra rb h rc rg; do
    cp serial_${f}_clean.log evidence/transcripts/$f.serial
done
cp bm651_fixtures.txt evidence/fixtures_before_boot.txt
# (no `ls evidence` echo here: it lists the gate's own transcript file, so two
# consecutive runs of an otherwise identical gate would differ by one word.)
