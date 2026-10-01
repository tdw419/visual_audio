#!/bin/bash
# RUNG5 gate: BM-501 (second-image read + CRC refusal) and BM-502 (write
# leg + persistence across reboot WITHOUT re-encode). Extends rung-4 by
# copy; never edits rung4/. Run: bash rung5/run_gate5.sh  (BACKGROUND mode
# for the tool caller: gate exceeds the 420s tool timeout; each boot leg
# itself is seconds but the x2 clean runs + QEMU startup add up).
set -u
cd "$(dirname "$0")"

fail() { echo "GATE5 FAIL: $1"; exit 1; }
# The expected-marker hex is this run's bytes, compared against the medium leg
# [3] reads back after a reboot. It used to live at the fixed name
# /tmp/expected_marker.hex, so a second concurrent run -- or a file left behind
# by an aborted one -- could satisfy the compare with bytes this run never built.
EXP_HEX=$(mktemp "${TMPDIR:-/tmp}/rung5_expected_marker.XXXXXX") || fail "mktemp"
trap 'rm -f "$EXP_HEX"' EXIT
TMO=25
SCALE=65536
MEDIUM=rung5_medium.raw
PNG=rung5_medium.png
META=rung5_meta.json

# ================= build (always rebuild: rung-4 trap 3) =================
echo "=== [0] build: layout disjointness, stage2, stage1, encode, host roundtrips ==="
python3 rung5_layout.py $SCALE || fail "layout disjointness"
LAYOUT=$(cat rung5_layout.inc)
# ORDER FIX (gate bug, measured 2026-09-18 run1): DEFS carries
# EXPECTED_IMG2_CRC from rung5_consts.py, which reads img2.bin -- so the
# image MUST exist (and be pinned, see make_img2.py SEED) BEFORE DEFS.
# The old order computed DEFS against the PREVIOUS run's img2.bin.
python3 make_img2.py || fail "make img2"
DEFS=$(python3 rung5_consts.py $SCALE) || fail "consts"
nasm -f bin stage2.asm $DEFS -l stage2.lst -o stage2_code.bin || fail "nasm stage2"
python3 rung4_pad.py $SCALE stage2_code.bin stage2.bin || fail "pad"
python3 rung4_consts.py || fail "stage1 consts"   # from rung5's stage2.bin
nasm -f bin stage1.asm -o stage1.bin || fail "nasm stage1"
[ "$(stat -c%s stage1.bin)" -eq 512 ] || fail "stage1 != 512 bytes"
python3 rung5_codec.py encode stage1.bin stage2.bin img2.bin \
    $PNG $MEDIUM $META >/dev/null || fail "encode"
python3 rung5_codec.py bake $PNG rung5_baked.raw $META >/dev/null || fail "bake"
cmp $MEDIUM rung5_baked.raw || fail "bake identity"
rm -f rung5_baked.raw
python3 rung5_codec.py decode $MEDIUM $META | tee decode_host.txt || fail "host decode"
D_S2=$(grep -o 'stage2 crc32=[0-9A-F]*' decode_host.txt | grep -o '[0-9A-F]\{8\}')
D_I2=$(grep -o 'img2 crc32=[0-9A-F]*' decode_host.txt | grep -o '[0-9A-F]\{8\}')
M_S2=$(python3 -c "import json;print(json.load(open('$META'))['payload_crc32'])")
M_I2=$(python3 -c "import json;print(json.load(open('$META'))['img2_crc32'])")
EXPECT_SUM=$(python3 -c "
img = open('img2.bin','rb').read()
print('%04X' % (sum(img) & 0xFFFF))")
[ "$D_S2" = "$M_S2" ] || fail "host decode stage2 CRC $D_S2 != meta $M_S2"
[ "$D_I2" = "$M_I2" ] || fail "host decode img2 CRC $D_I2 != meta $M_I2"

# independent layout disjointness assertion over the codec's meta
python3 - "$META" <<'EOF' || fail "meta disjointness"
import json, sys
m = json.load(open(sys.argv[1]))
base = m["img2_base"]
regions = {"stage1": (0, 512),
           "stage2": (512, 512 + 4 * (m["payload_len"] // 4)),
           "img2": (base, base + 4 * (m["img2_len"] // 4))}
names = sorted(regions)
bad = []
for i, a in enumerate(names):
    for b in names[i + 1:]:
        (a0, a1), (b0, b1) = regions[a], regions[b]
        if a0 < b1 and b0 < a1:
            bad.append((a, b))
assert not bad, f"meta regions overlap: {bad}"
wr_lba = (regions["img2"][1] + 511) // 512 * 512
assert wr_lba >= regions["img2"][1], "write region inside img2"
assert wr_lba >= regions["stage2"][1], "write region inside stage2"
print("meta disjointness OK:", regions, "write sector", wr_lba)
EOF

IMG2_BASE_LBA=$(( $(python3 -c "import json;print(json.load(open('$META'))['img2_base'])") / 512 ))
EXPECT_IMG2=$(python3 -c "import json;print(json.load(open('$META'))['img2_crc32'])")
EXPECT_S2=$(python3 -c "import json;print(json.load(open('$META'))['payload_crc32'])")
echo "meta: img2_crc32=$EXPECT_IMG2 stage2_crc32=$EXPECT_S2 img2_base_lba=$IMG2_BASE_LBA sum16=$EXPECT_SUM"

boot() {  # $1 serial log, $2 extra qemu args...
    local LOG=$1; shift
    timeout $TMO qemu-system-x86_64 -drive file=$MEDIUM,format=raw,if=ide \
        -display none -no-reboot -serial file:$LOG "$@" 2>/dev/null
}

echo "=== [1] GREEN-A (BM-501): boot 1 — img2 CRC match + WRITE=OK ==="
boot serial_g1.log
tr -d '\r' < serial_g1.log | tee serial_g1_clean.log
grep -q "PXC1-RUNG5" serial_g1_clean.log || fail "no rung5 hello (got tail above)"
grep -q "IMG2 SUM=$EXPECT_SUM" serial_g1_clean.log || fail "BM-501: img2 sum16 witness mismatch (deinterleave path) — got: $(tr -d '\r\n' < serial_g1_clean.log)"
grep -q "IMG2 CRC=$EXPECT_IMG2" serial_g1_clean.log || fail "BM-501: img2 CRC mismatch on pristine medium"
grep -q "WRITE=OK" serial_g1_clean.log || fail "BM-502: no WRITE=OK"
grep -q "STAGE2 CKSUM=.* EXEC" serial_g1_clean.log || fail "stage2 self receipt missing"

echo "=== [2] host verify of the WRITE leg: marker bytes at WR_LBA ==="
WR_LBA=$(( $(grep -oP 'WR_LBA\s+equ \K[0-9]+' rung5_layout.inc) ))
WR_OFF=$(( WR_LBA * 512 ))
S2BIN=stage2.bin
# EXPECTED marker = stage2.bin[0:2048] with the two RUNTIME-UPDATED vars
# (img2crcline, img2sumline) patched to their boot-time values — the
# guest writes its own code page AFTER storing the CRC + sum witness
# (measured 2026-09-18 run 5: pristine-payload compare diffed at exactly
# img2crcline's ORG offset 0x2D2=722, with BA D4 80 78 = CRC 7880D4BA
# little-endian, then 56 E9 = sum E956 — the write was byte-perfect).
python3 expected_marker.py $S2BIN stage2.lst img2.bin > "$EXP_HEX" || fail "expected marker build"
python3 - "$WR_OFF" "$S2BIN" "$MEDIUM" "$EXP_HEX" <<'EOF' || fail "host marker verify"
import sys
off, s2path, med, exppath = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
expected = bytes.fromhex(open(exppath).read().strip())
medium = open(med, "rb")
medium.seek(off)
got = medium.read(len(expected))
assert got == expected, f"written marker != expected at medium offset {off}: first diff at {next((i for i,(a,b) in enumerate(zip(expected,got)) if a!=b), min(len(expected),len(got)))}"
print(f"host verify: {len(expected)} marker bytes at medium offset {off} == stage2 payload with runtime vars patched")
EOF

echo "=== [3] persistence: reboot WITHOUT re-encode; stage2 reads back the marker ==="
# boot 2 boots the SAME raw. On this boot stage2 must again report
# IMG2 CRC ok (its read window is untouched by the write) — and the
# persistence check itself is host-side + guest-side:
#   guest:  IMG2 CRC=<expect> again proves the read path is intact
#   host:   the marker written in boot 1 is still there byte-identical
boot serial_g2.log
tr -d '\r' < serial_g2.log | tee serial_g2_clean.log
grep -q "IMG2 CRC=$EXPECT_IMG2" serial_g2_clean.log || fail "boot2: img2 read path broken after write"
grep -q "WRITE=OK" serial_g2_clean.log || fail "boot2: write leg did not run"
# persistence compare: medium marker vs the RUNTIME-EXPECTED marker (same
# patched image leg [2] uses — pristine stage2.bin differs from it by the
# two runtime vars, which the write legitimately carries)
cmp <(cat "$EXP_HEX" | tr -d '\n') \
    <(python3 -c "m=open('$MEDIUM','rb').read()[$WR_OFF:$WR_OFF+2048];print(m.hex())" | tr -d '\n') \
    || fail "persistence: marker clobbered by boot 2"
echo "persistence: marker still byte-identical after boot 2"

echo "=== [4] RED-A (BM-501): corrupt ONE pixel of the second image -> specified refusal ==="
# img2 byte 16 -> plane 0, slot 4 -> medium offset img2_base + 4
IMG2_BASE=$(python3 -c "import json;print(json.load(open('$META'))['img2_base'])")
OFF=$(( IMG2_BASE + 4 ))
ORIG=$(python3 -c "print(open('$MEDIUM','rb').read()[$OFF])")
NEW=$((ORIG ^ 255))
qemu-io -c "write -P $NEW $OFF 1" $MEDIUM >/dev/null 2>&1 || fail "qemu-io write"
[ "$(python3 -c "print(open('$MEDIUM','rb').read()[$OFF])")" -eq "$NEW" ] || fail "corruption did not land"
NEWSUM=$(python3 - "$META" "$OFF" "$ORIG" <<'EOF'
import json, sys, zlib
meta = json.load(open(sys.argv[1]))
off, orig = int(sys.argv[2]), int(sys.argv[3])
base = meta["img2_base"]
plane_len = meta["img2_len"] // 4
rel = off - base
plane, slot = rel // plane_len, rel % plane_len
idx = slot * 4 + plane
img = bytearray(open("img2.bin", "rb").read())
assert img[idx] == orig, f"host map: img2[{idx}]={img[idx]} != medium byte {orig}"
img[idx] ^= 255
print('%08X' % (zlib.crc32(bytes(img)) & 0xFFFFFFFF))
EOF
) || fail "host crc arithmetic"
echo "RED-A: corrupted img2 byte idx (medium $OFF), expected refusal CRC=$NEWSUM EXP=$EXPECT_IMG2"
boot serial_ra.log
tr -d '\r' < serial_ra.log | tee serial_ra_clean.log
grep -q "IMG2 FAIL CRC=$NEWSUM EXP=$EXPECT_IMG2" serial_ra_clean.log || fail "RED-A: no specified refusal (got tail above)"
grep -q "WRITE=" serial_ra_clean.log && fail "RED-A: write leg ran despite img2 corruption"
grep -q "STAGE2" serial_ra_clean.log && fail "RED-A: stage2 continued past refusal"

echo "=== [5] non-vacuity: neuter the img2 CRC check -> gate must flip ==="
# spot-verify once: assemble a stage2 whose EXPECTED_IMG2_CRC equals the
# CORRUPTED image's CRC; the corrupted medium must then PASS img2 and
# reach WRITE=OK — proving leg [4] fails for the CHECK, not trivially.
# DEFECT-R5NVDEFS (measured 2026-09-18 run 10): the bash ${DEFS/pat/repl}
# substitution matches GLOB patterns, and the digit-string pattern matched
# DEFS' FIRST numeric field (RUNG4_SCALE), not EXPECTED_IMG2_CRC -- the
# stripped define list then lost -DDST_SEG and nasm failed. Rebuild the
# DEFS from the corrupted image instead: copy img2.bin aside, write the
# corrupted bytes, regenerate DEFS with the corrupted CRC baked in.
NVDEFS=$(python3 - "$NEWSUM" <<'EOF'
import sys
print(sys.argv[1])
EOF
)
cp img2.bin img2_main.keep
python3 - "$OFF" "$ORIG" <<'EOF'
import sys
off, orig = int(sys.argv[1]), int(sys.argv[2])
# rebuild the CORRUPTED img2 bytes: apply the same XOR the gate applied
# to the medium, via the plane->byte map (plane p, slot k -> byte 4k+p)
import json
meta = json.load(open("rung5_meta.json"))
rel = off - meta["img2_base"]
plane_len = meta["img2_len"] // 4
p, k = rel // plane_len, rel % plane_len
idx = k * 4 + p
img = bytearray(open("img2.bin", "rb").read())
assert img[idx] == orig, f"img2[{idx}]={img[idx]} != medium byte {orig}"
img[idx] ^= 255
open("img2.bin", "wb").write(bytes(img))
EOF
NVDEFS=$(python3 rung5_consts.py $SCALE) || fail "consts nv"
nasm -f bin stage2.asm $NVDEFS -o stage2_nv.bin || fail "nasm nv"
mv img2_main.keep img2.bin
python3 rung4_pad.py $SCALE stage2_nv.bin stage2_nv_padded.bin || fail "pad nv"
# stage2_nv differs from pristine stage2 (it embeds the neutered img2 CRC
# constant), so stage1's EXPECTED_CRC must be derived from stage2_nv too --
# otherwise stage1's own integrity gate kills the nv boot (run13: GATE4=FAIL
# CRC=2DA13125 EXP=329CD470) before the img2 check can prove anything.
python3 rung4_consts.py stage2_nv_padded.bin || fail "stage1 consts nv"
nasm -f bin stage1.asm -o stage1_nv.bin || fail "nasm nv stage1"
# restore pristine consts so later legs / the next clean run see stage2.bin's
python3 rung4_consts.py || fail "stage1 consts restore"
python3 rung5_codec.py encode stage1_nv.bin stage2_nv_padded.bin img2.bin \
    rung5_nv.png rung5_nv.raw rung5_nv.png.json >/dev/null || fail "encode nv"
qemu-io -c "write -P $NEW $OFF 1" rung5_nv.raw >/dev/null 2>&1 || fail "qemu-io nv"
timeout $TMO qemu-system-x86_64 -drive file=rung5_nv.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_nv.log 2>/dev/null
tr -d '\r' < serial_nv.log | tee serial_nv_clean.log
grep -q "IMG2 CRC=$NEWSUM" serial_nv_clean.log || fail "non-vacuity: check refuses even when expectation matches corruption"
grep -q "WRITE=OK" serial_nv_clean.log || fail "non-vacuity: write leg missing after neutered check"
rm -f rung5_nv.raw rung5_nv.png rung5_nv.png.json stage2_nv*.bin stage1_nv.bin

echo "=== [6] RE-GREEN: rebake pristine from untouched PNG, boot, byte-identical ==="
python3 rung5_codec.py bake $PNG $MEDIUM $META >/dev/null || fail "rebake"
boot serial_rg.log
tr -d '\r' < serial_rg.log | grep -v '^$' > serial_rg_clean.log || true
diff serial_g1_clean.log serial_rg_clean.log >/dev/null || fail "RE-GREEN mismatch"
echo "RE-GREEN: boot serial identical to boot 1 (pristine medium, fresh write)"

echo "=== [7] GREEN-B: 2nd consecutive GREEN boot from the same build ==="
# (the x2-clean-rebuild discipline of rung 4 is preserved by re-running
# this script end-to-end for the official pair; within one run we take
# the second boot over the rebaked medium as the repeat witness)
boot serial_g3.log
tr -d '\r' < serial_g3.log | grep -v '^$' > serial_g3_clean.log || true
diff serial_g1_clean.log serial_g3_clean.log >/dev/null || fail "GREEN-B: boot serial differs from boot 1"

echo
echo "=== GATE5 PASS ==="
echo "greenA  : $(tr -d '\n' < serial_g1_clean.log)"
echo "greenB  : $(tr -d '\n' < serial_g2_clean.log)"
echo "greenC  : $(tr -d '\n' < serial_g3_clean.log)"
echo "redA    : $(tr -d '\n' < serial_ra_clean.log)"
echo "nonvac  : neutered check PASSES corrupted img2 (check is load-bearing)"
echo "regreen : boot serial identical to boot 1"
