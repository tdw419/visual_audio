#!/bin/bash
# End-to-end gate: pixels -> booting CPU -> serial receipt.
# Proves the bare-metal boot chain at 512-byte scale. See RECEIPT.md.
set -u
cd "$(dirname "$0")"

PLUGIN=pxc1_nbd_plugin.py
PNG=boot_sector.png

# Socket, nbdkit's stderr and the plugin's per-request trace: one directory this
# run owns. The socket moved out of /tmp/pxc1_nbd.sock because a second gate
# would unlink the first one's live socket and every new client would attach to a
# medium it did not build; the rm -f below stays because leg [6] restarts on the
# same name after SIGTERM leaves the file behind.
SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/pxc1_gate.XXXXXX")
SOCK="$SCRATCH/pxc1_nbd.sock"
TRACE="$SCRATCH/pxc1_trace.log"
DRIVE="file.driver=nbd,file.server.type=unix,file.server.path=$SOCK,format=raw,if=ide"

cleanup() {
    for p in $(pgrep -x nbdkit); do
        if grep -q pxc1_nbd_plugin /proc/$p/cmdline 2>/dev/null; then kill $p; fi
    done
    rm -f $SOCK
}
trap 'cleanup; rm -rf "$SCRATCH"' EXIT

fail() { echo "GATE FAIL: $1"; exit 1; }

echo "=== [0] rebuild + encode + static roundtrip ==="
nasm -f bin boot.asm -o boot.bin || fail "nasm"
python3 pxc1_boot_codec.py encode boot.bin $PNG >/dev/null || fail "encode"
python3 pxc1_boot_codec.py decode $PNG decoded.bin >/dev/null || fail "decode"
cmp boot.bin decoded.bin || fail "roundtrip"
EXPECT=$(python3 -c "print('%04X' % (sum(open('boot.bin','rb').read()) % 65536))")
echo "expected CKSUM=$EXPECT"

echo "=== [1] start pixel-backed NBD server ==="
cleanup
rm -f $SOCK
PXC1_NBD_TRACE="$TRACE" nbdkit -U $SOCK python ./$PLUGIN png=$PWD/$PNG 2>"$SCRATCH/nbdkit_gate_1.log" &
for i in $(seq 1 20); do [ -S $SOCK ] && break; sleep 0.5; done
[ -S $SOCK ] || fail "nbdkit socket never appeared"

echo "=== [2] GREEN: boot from live pixels ==="
timeout 8 qemu-system-x86_64 -drive $DRIVE -display none -no-reboot \
    -serial file:serial_g.log 2>/dev/null
grep -q "CKSUM=$EXPECT EXEC" serial_g.log || fail "green receipt"

echo "=== [3] RED-A: corrupt byte 0, guest must report different CKSUM ==="
qemu-io --image-opts "driver=nbd,server.type=unix,server.path=$SOCK" \
    -c 'write -P 90 0 1' >/dev/null 2>&1     # NOTE: -P is DECIMAL (0x5A)
timeout 8 qemu-system-x86_64 -drive $DRIVE -display none -no-reboot \
    -serial file:serial_ra.log 2>/dev/null
grep -q "CKSUM=$EXPECT" serial_ra.log && fail "RED-A: checksum did not change"
grep -q "EXEC" serial_ra.log || fail "RED-A: nop-for-nop swap did not execute"

echo "=== [4] RED-B: destroy 55AA signature, expect NO execution ==="
qemu-io --image-opts "driver=nbd,server.type=unix,server.path=$SOCK" \
    -c 'write -P 0 510 2' >/dev/null 2>&1
timeout 8 qemu-system-x86_64 -drive $DRIVE -display none -no-reboot \
    -serial file:serial_rb.log 2>/dev/null
[ "$(wc -c < serial_rb.log)" -eq 0 ] || fail "RED-B: serial output present"

echo "=== [5] base PNG immutable ==="
python3 pxc1_boot_codec.py decode $PNG decoded2.bin >/dev/null
cmp boot.bin decoded2.bin || fail "PNG changed under journal writes"

echo "=== [6] RE-GREEN: restart server (fresh decode), journal evaporates ==="
cleanup
rm -f $SOCK
PXC1_NBD_TRACE="$TRACE" nbdkit -U $SOCK python ./$PLUGIN png=$PWD/$PNG 2>"$SCRATCH/nbdkit_gate_6.log" &
for i in $(seq 1 20); do [ -S $SOCK ] && break; sleep 0.5; done
[ -S $SOCK ] || fail "restart: socket never appeared"
timeout 8 qemu-system-x86_64 -drive $DRIVE -display none -no-reboot \
    -serial file:serial_rg.log 2>/dev/null
diff -q serial_g.log serial_rg.log >/dev/null || fail "RE-GREEN mismatch"

echo
echo "=== GATE PASS ==="
echo "green : $(cat serial_g.log | tr -d '\r')"
echo "redA  : $(cat serial_ra.log | tr -d '\r')"
echo "redB  : $(wc -c < serial_rb.log) serial bytes"
echo "png   : sha-verified after all journal writes"
echo "regreen: byte-identical to green"
