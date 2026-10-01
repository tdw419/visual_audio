#!/bin/bash
# RUNG2 gate: the LOADER decodes the payload from pixel planes itself.
# No nbdkit, no NBD, no host server: QEMU sees a plain raw file whose bytes
# ARE an RGBA pixel stream, and the MBR does the pixel-domain work
# (int 13h read -> channel-plane de-interleave -> checksum gate -> jump).
# See RECEIPT_RUNG2.md.
#
# SCOPE NOTE: leg [5]'s absence scan is O(n*m) — every 16-byte payload window
# is memchr'd over the whole medium. Acceptable at this ~144B payload; it
# MUST be redesigned (block-hash or suffix-array) before any kernel-sized
# payload reuses it.
set -u
cd "$(dirname "$0")"

fail() { echo "GATE FAIL: $1"; exit 1; }
TMO=8   # qemu legs: guest reaches hlt in ~2s; timeout bounds the leg

echo "=== [0] build + encode + host-side roundtrips ==="
nasm -f bin stage2.asm -o stage2.bin || fail "nasm stage2"
python3 - <<'EOF' || fail "stage1 consts"
s2 = open("stage2.bin", "rb").read()
s2 += b"\x00" * ((-len(s2)) % 4)
plane = len(s2) // 4
sectors = max(1, (len(s2) + 511) // 512)
consts = (f"PLANE_LEN     equ {plane}\n"
          f"PAYLOAD_LEN   equ {len(s2)}\n"
          f"PAYLOAD_SECTORS equ {sectors}\n"
          f"EXPECTED_SUM  equ 0x{sum(s2) % 65536:04X}\n")
open("stage1_const.inc", "w").write(consts)
print(f"stage2 padded={len(s2)}B plane={plane}B sectors={sectors} "
      f"EXPECT2={sum(s2)%65536:04X}")
EOF
nasm -f bin stage1.asm -o stage1.bin || fail "nasm stage1"
[ "$(stat -c%s stage1.bin)" -eq 512 ] || fail "stage1 != 512 bytes"
python3 rung2_codec.py encode stage1.bin stage2.bin rung2_medium.png \
    rung2_medium.raw rung2_meta.json >/dev/null || fail "encode"
python3 rung2_codec.py bake rung2_medium.png rung2_baked.raw \
    rung2_meta.json >/dev/null || fail "bake"
cmp rung2_medium.raw rung2_baked.raw || fail "bake identity (png->raw)"
rm -f rung2_baked.raw
python3 rung2_codec.py decode rung2_medium.raw rung2_meta.json \
    payload_host.bin >/dev/null || fail "decode raw"
python3 rung2_codec.py decode rung2_medium.png rung2_meta.json \
    payload_host_png.bin >/dev/null || fail "decode png"
cmp payload_host.bin payload_host_png.bin || fail "png/raw decodes disagree"
cmp stage2.bin payload_host.bin || fail "decode != stage2.bin"
EXPECT2=$(python3 -c "import json;print(json.load(open('rung2_meta.json'))['payload_sum16'])")
echo "expected STAGE2 CKSUM=$EXPECT2"

echo "=== [0b] pre-flight: every boot leg starts from a known-bootable medium ==="
# (1) boot signature present; (2) the raw medium is byte-identical to the PNG
# pixel stream (same PIL-free identity as the leg-[0] bake check). Guards
# against a stale/partial medium surviving into the boot legs.
python3 - <<'EOF' || fail "pre-flight 55AA"
med = open("rung2_medium.raw", "rb").read()
assert med[510:512] == b"\x55\xaa", \
    f"boot signature destroyed: {med[510:512].hex()} (want 55aa)"
EOF
python3 rung2_codec.py bake rung2_medium.png rung2_preflight.raw \
    rung2_meta.json >/dev/null || fail "pre-flight bake"
cmp rung2_medium.raw rung2_preflight.raw \
    || fail "pre-flight: raw medium != PNG pixel stream"
rm -f rung2_preflight.raw
echo "pre-flight OK: 55AA present, medium == PNG pixel stream"

echo "=== [1] GREEN: boot; MBR decodes pixel planes, stage2 EXECs ==="
timeout $TMO qemu-system-x86_64 -drive file=rung2_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_g.log 2>/dev/null
grep -q "GATE=PASS" serial_g.log || fail "green: no GATE=PASS (got: $(tr -d '\r' < serial_g.log))"
grep -q "STAGE2 CKSUM=$EXPECT2 EXEC" serial_g.log || fail "green receipt"

echo "=== [2] RED-A: corrupt one payload PIXEL -> loader must refuse ==="
# payload byte 16 -> plane 0, slot 4 -> medium byte 512+4 = 516
OFF=516
ORIG=$(python3 -c "print(open('rung2_medium.raw','rb').read()[$OFF])")
NEW=$((ORIG ^ 255))
# Audit finding: a corruption write that is a NO-OP (NEW == ORIG, e.g. a
# blind `write -P 0` over a 0x00 byte) lands nothing, corrupts nothing, and
# the leg would boot GREEN — a corruption test that cannot fail. Assert the
# flip actually flips before trusting the landed-check below.
[ "$ORIG" -ne "$NEW" ] \
    || fail "RED-A: flip is a no-op (ORIG == NEW = $ORIG); corruption cannot land"
qemu-io -c "write -P $NEW $OFF 1" rung2_medium.raw >/dev/null 2>&1 || fail "qemu-io write"
[ "$(python3 -c "print(open('rung2_medium.raw','rb').read()[$OFF])")" -eq "$NEW" ] \
    || fail "corruption did not land"
NEWSUM=$(EXPECT2=$EXPECT2 ORIG=$ORIG NEW=$NEW python3 -c \
    "import os;print('%04X' % ((int(os.environ['EXPECT2'],16)-int(os.environ['ORIG'])+int(os.environ['NEW']))%65536))")
timeout $TMO qemu-system-x86_64 -drive file=rung2_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_ra.log 2>/dev/null
grep -q "GATE=FAIL SUM=$NEWSUM" serial_ra.log || fail "RED-A: no specified failure (got: $(tr -d '\r' < serial_ra.log))"
grep -q "EXEC" serial_ra.log && fail "RED-A: stage2 executed despite corruption"
echo "loader refused: GATE=FAIL SUM=$NEWSUM (arithmetic: $EXPECT2 - $ORIG + $NEW mod 2^16)"

echo "=== [3] RED-B: destroy 55AA signature, expect NO execution ==="
qemu-io -c "write -P 0 510 2" rung2_medium.raw >/dev/null 2>&1 || fail "qemu-io write"
timeout $TMO qemu-system-x86_64 -drive file=rung2_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_rb.log 2>/dev/null
[ "$(wc -c < serial_rb.log)" -eq 0 ] || fail "RED-B: serial output present"

echo "=== [4] rebake pristine medium from PNG (PNG untouched through [2][3]) ==="
python3 rung2_codec.py bake rung2_medium.png rung2_medium.raw \
    rung2_meta.json >/dev/null || fail "rebake"

echo "=== [5] ABSENCE: no 16-byte payload window exists contiguously in the payload region ==="
python3 - <<'EOF' || fail "absence"
med = open("rung2_medium.raw", "rb").read()
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
# payload region (offsets >= 512, where the channel planes live) -> a
# linear reader cannot recover/copy the payload; de-interleave required.
# Matches inside [0,512) are stage1's own contiguous copy: the payload
# shares its helper code with stage1 byte-for-byte, so those hits are
# stage1's storage, not the payload's. Counted, not ignored.
leaks, shared = [], 0
for i in range(len(s2) - 15):
    w = s2[i:i + 16]
    if med.find(w, 512) != -1:
        leaks.append(i)
    elif med.find(w) != -1:
        shared += 1
assert not leaks, f"payload windows contiguous in payload region: {leaks[:5]}"
print(f"absence proven: 0 of {len(s2)-15} 16-byte payload windows occur "
      f"contiguously in the payload region; {shared} windows match only "
      f"inside stage1's contiguous copy (shared helper code); "
      f"planted-probe control OK")
EOF

echo "=== [6] RE-GREEN: boot the rebaked medium, serial byte-identical ==="
timeout $TMO qemu-system-x86_64 -drive file=rung2_medium.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:serial_rg.log 2>/dev/null
diff -q serial_g.log serial_rg.log >/dev/null || fail "RE-GREEN mismatch"

echo
echo "=== GATE PASS ==="
echo "green : $(tr -d '\r' < serial_g.log | tr '\n' ' ')"
echo "redA  : $(tr -d '\r' < serial_ra.log | tr '\n' ' ')"
echo "redB  : $(wc -c < serial_rb.log) serial bytes"
echo "absence: 0 of 129 payload 16B-windows contiguous in the payload region"
echo "regreen: byte-identical to green"
