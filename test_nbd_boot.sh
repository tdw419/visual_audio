#!/bin/bash
set -e

killall qemu-system-x86_64 2>/dev/null || true
# CRITICAL freshness guard: remove the serial log BEFORE launching qemu so the
# grep-based login check can never match stale content from a previous run.
# Without this, the check races qemu startup and can declare SUCCESS against
# an untouched log file (qemu is killed before it truncates/writes it).
rm -f /tmp/qemu_serial_nbd.log
cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/OVMF_VARS_NBD.fd

echo "Booting Ubuntu via V4 Pixel Bootloader, RootFS served via NBD..."
qemu-system-x86_64 \
    -machine q35 \
    -m 2048 \
    -smp 2 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/OVMF_VARS_NBD.fd \
    -drive file=/tmp/ubuntu_v4_efi.img,format=raw,if=virtio \
    -drive file=nbd:127.0.0.1:10809,format=raw,if=virtio,readonly=on \
    -nographic \
    -serial file:/tmp/qemu_serial_nbd.log \
    -monitor none &
QEMU_PID=$!

echo "Waiting for login prompt in serial log..."
RUN_START=$(date +%s)
timeout 600 bash -c 'until grep -q "ubuntu login:" /tmp/qemu_serial_nbd.log 2>/dev/null; do sleep 2; echo -n "."; done' || true
echo

LOG_MTIME=$(stat -c %Y /tmp/qemu_serial_nbd.log 2>/dev/null || echo 0)
if grep -q "ubuntu login:" /tmp/qemu_serial_nbd.log && [ "$LOG_MTIME" -ge "$RUN_START" ]; then
    echo "SUCCESS: Ubuntu booted from NBD tiles! (log mtime $LOG_MTIME >= run start $RUN_START)"
else
    echo "FAILED: Did not reach login prompt (or log is stale: mtime $LOG_MTIME, run start $RUN_START)."
    tail -n 20 /tmp/qemu_serial_nbd.log
fi

kill -9 $QEMU_PID || true
