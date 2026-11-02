#!/bin/bash
# RUNG4 gate: the LOADER decodes a >=64 KB payload from pixel planes itself.
# Rung-2 gate discipline at scale. No nbdkit, no NBD, no host server: QEMU
# sees a plain raw file whose bytes ARE an RGBA pixel stream, and the MBR
# streams it through a chunk window (EDD AH=42h loop), de-interleaves the
# four channel planes, CRC32-gates the full image, and only then transfers
# control. See ROADMAP.md Rung 4 + RECEIPT_RUNG4.md.
set -u
cd "$(dirname "$0")"

fail() { echo "GATE FAIL: $1"; exit 1; }
TMO=25   # qemu legs: 256 KB decode + CRC in guest takes seconds; bounds the leg
SCALE_DEFAULT=65536   # 64 KB
SCALE_BIG=262144      # 256 KB
CHUNK_SECTORS=8       # 4 KB chunks -> 4 chunks/plane at 64 KB, 16 at 256 KB

run_scale() {  # $1 = SCALE, $2 = serial log tag
    local SCALE=$1 TAG=$2
    nasm -f bin stage2.asm -DRUNG4_SCALE=$SCALE -o stage2_code.bin || fail "nasm stage2"
    python3 rung4_pad.py $SCALE stage2_code.bin stage2.bin || fail "pad to scale"
    python3 rung4_consts.py || fail "stage1 consts"
    nasm -f bin stage1.asm -o stage1.bin || fail "nasm stage1"
    [ "$(stat -c%s stage1.bin)" -eq 512 ] || fail "stage1 != 512 bytes"
    python3 rung4_codec.py encode stage1.bin stage2.bin rung4_medium.png \
        rung4_medium.raw rung4_meta.json >/dev/null || fail "encode"
    python3 rung4_codec.py bake rung4_medium.png rung4_baked.raw \
        rung4_meta.json >/dev/null || fail "bake"
    cmp rung4_medium.raw rung4_baked.raw || fail "bake identity (png->raw)"
    rm -f rung4_baked.raw
    python3 rung4_codec.py decode rung4_medium.raw rung4_meta.json \
        payload_host.bin >/dev/null || fail "decode raw"
    python3 rung4_codec.py decode rung4_medium.png rung4_meta.json \
        payload_host_png.bin >/dev/null || fail "decode png"
    cmp payload_host.bin payload_host_png.bin || fail "png/raw decodes disagree"
    cmp stage2.bin payload_host.bin || fail "decode != stage2.bin"

    echo "=== [1] GREEN ($TAG): boot; MBR streams+decodes $SCALE B, stage2 EXECs ==="
    timeout $TMO qemu-system-x86_64 -drive file=rung4_medium.raw,format=raw,if=ide \
        -display none -no-reboot -serial file:serial_g_$TAG.log 2>/dev/null
    grep -q "GATE4=PASS" serial_g_$TAG.log || fail "green: no GATE4=PASS (got: $(tr -d '\r' < serial_g_$TAG.log | tail -3))"
    grep -q "STAGE2 SIZE=$((SCALE/1024)) KB" serial_g_$TAG.log || fail "green size receipt"
    grep -q "STAGE2 CKSUM=.* EXEC" serial_g_$TAG.log || fail "green exec receipt"
}

# ================== legs at 64 KB (the rung's scale claim) ==================
run_scale $SCALE_DEFAULT 64k

EXPECT2=$(python3 -c "import json;print(json.load(open('rung4_meta.json'))['payload_crc32'])")
echo "expected STAGE2 CRC32=$EXPECT2"

echo "=== [2] RED-A: corrupt one payload PIXEL -> loader must refuse, naming CRC ==="
# payload byte 16 -> plane 0, slot 4 -> medium byte 512+4 = 516
OFF=516
ORIG=$(python3 -c "print(open('rung4_medium.raw','rb').read()[$OFF])")
NEW=$((ORIG ^ 255))
qemu-io -c "write -P $NEW $OFF 1" rung4_medium.raw >/dev/null 2>&1 || fail "qemu-io write"
[ "$(python3 -c "print(open('rung4_medium.raw','rb').read()[$OFF])")" -eq "$NEW" ] \
    || fail "corruption did not land"
NEWSUM=$(EXPECT2=$EXPECT2 ORIG=$ORIG NEW=$NEW python3 - <<'EOF'
import os, zlib, json
meta = json.load(open('rung4_meta.json'))
# host arithmetic cross-check: recompute the corrupted payload's CRC
# from the host-decoded pristine payload with the one byte substituted.
# (The decoded payload equals stage2.bin; patch byte OFF-512.. no: the
# medium offset maps back to plane/slot -> payload index = slot*4 + plane.)
p = bytearray(open('payload_host.bin','rb').read())
slot = (512 - 512 + 4) // 1  # computed below properly
off_med = 516
plane = (off_med - 512) // ((meta['payload_len'])//4)
sloti = (off_med - 512) % ((meta['payload_len'])//4)
idx = sloti * 4 + plane
p[idx] ^= 255
print('%08X' % (zlib.crc32(bytes(p)) & 0xFFFFFFFF))
EOF
) || fail "host crc arithmetic"
timeout $TMO qemu-system-x86_64 -drive file=rung4_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_ra.log 2>/dev/null
grep -q "GATE4=FAIL CRC=$NEWSUM" serial_ra.log || fail "RED-A: no specified failure (got: $(tr -d '\r' < serial_ra.log | tail -3))"
grep -q "EXP=$EXPECT2" serial_ra.log || fail "RED-A: expected CRC not printed"
grep -q "STAGE2" serial_ra.log && fail "RED-A: stage2 executed despite corruption"
echo "loader refused: GATE4=FAIL CRC=$NEWSUM EXP=$EXPECT2 (host arithmetic agrees)"

echo "=== [3] RED-B: destroy 55AA signature, expect NO execution ==="
qemu-io -c "write -P 0 510 2" rung4_medium.raw >/dev/null 2>&1 || fail "qemu-io write"
timeout $TMO qemu-system-x86_64 -drive file=rung4_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_rb.log 2>/dev/null
[ "$(wc -c < serial_rb.log)" -eq 0 ] || fail "RED-B: serial output present"

echo "=== [4] rebake pristine medium from PNG (PNG untouched through [2][3]) ==="
python3 rung4_codec.py bake rung4_medium.png rung4_medium.raw \
    rung4_meta.json >/dev/null || fail "rebake"

echo "=== [5] ABSENCE at scale: no 16-byte payload window contiguous in payload region ==="
python3 - <<'EOF' || fail "absence"
import json
meta = json.load(open("rung4_meta.json"))
plane = meta["payload_len"] // 4
# PERF (measured 2026-09-17): reading the FULL 64 MB raw disk here plus
# the naive per-window bytes.find made this leg take minutes; only the
# [0, 512+4*plane) prefix is meaningful, and the md5 window index below
# is exact (byte-compare confirmed on hit). Leg now runs <2s.
med = open("rung4_medium.raw", "rb").read(512 + 4 * plane)
s2 = open("payload_host.bin", "rb").read()
s1 = open("stage1.bin", "rb").read()
# control 1: stage1 (consecutive packing, by design) is findable at 0
assert med.find(s1[:16]) == 0, "control failed: stage1 head not found at 0"
# control 2: the search itself works — plant a probe, find it, discard
probe = b"ABSENCE_PROBE_01"
assert probe not in med
med2 = med[:60000] + probe + med[60016:]
assert med2.find(probe) == 60000, "control failed: planted probe not found"
del med2
# claim: no 16-byte payload window occurs contiguously anywhere in the
# payload region [512, 512+4*plane) -> a linear reader cannot recover or
# copy the payload; de-interleave required. Matches inside [0,512) are
# stage1's own contiguous copy: stage1 shares helper code with stage2
# byte-for-byte, so those hits are stage1's storage, not the payload's.
# PERF (measured 2026-09-17): naive per-window bytes.find over the region
# is O(65521 x 65521) byte comparisons and runs minutes; the md5 index
# below is exact (byte-compare confirmed on hit) and runs <1s.
leaks, shared = [], 0
region = med[512:512 + 4 * plane]
import hashlib
idx = {}
for j in range(len(region) - 15):
    idx.setdefault(hashlib.md5(region[j:j+16]).digest(), []).append(j)
for i in range(len(s2) - 15):
    w = s2[i:i + 16]
    hits = idx.get(hashlib.md5(w).digest())
    if hits:
        if any(region[j:j+16] == w for j in hits):
            leaks.append(i)
        continue
    if med.find(w) != -1:
        shared += 1
assert not leaks, f"payload windows contiguous in payload region: {leaks[:5]}"
print(f"absence proven at {meta['payload_len']}B: 0 of {len(s2)-15} 16-byte "
      f"payload windows occur contiguously in the payload region; {shared} "
      f"windows match only inside stage1's contiguous copy (shared helper "
      f"code); planted-probe control OK")
EOF

echo "=== [6] RE-GREEN: boot the rebaked medium, serial byte-identical ==="
timeout $TMO qemu-system-x86_64 -drive file=rung4_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_rg.log 2>/dev/null
diff -q serial_g_64k.log serial_rg.log >/dev/null || fail "RE-GREEN mismatch"

echo "=== [7] scale sweep: 256 KB GREEN (the loop really iterates) ==="
run_scale $SCALE_BIG 256k
grep -q "GATE4=PASS" serial_g_256k.log || fail "256k green"
grep -q "STAGE2 SIZE=256 KB" serial_g_256k.log || fail "256k size receipt"
# restore the 64 KB build as the standing artifact set
run_scale $SCALE_DEFAULT 64k

echo
echo "=== GATE PASS ==="
echo "green64k : $(tr -d '\r' < serial_g_64k.log | tr '\n' ' ')"
echo "redA     : $(tr -d '\r' < serial_ra.log | tr '\n' ' ')"
echo "redB     : $(wc -c < serial_rb.log) serial bytes"
echo "green256k: $(tr -d '\r' < serial_g_256k.log | tr '\n' ' ')"
echo "regreen  : byte-identical to green64k"
