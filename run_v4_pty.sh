#!/bin/bash
set -ex

# Create a master PTY
SERIAL_PTY=$(socat -d -d pty,link=/tmp/qemu_serialpty,raw,echo=0,waitslave pty,raw,echo=0 2>&1 | grep "PTY is" | head -1 | awk '{print $NF}' | tr -d "'" &)
sleep 1

# Use stdio instead - simpler and more reliable
timeout 90s qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial mon:stdio < /dev/null | tee /tmp/qemu_serial_interactive.log &
QEMU_PID=$!

# Wait for boot (give it enough time)
sleep 30

# Check if we reached login prompt
if grep -q "ubuntu login:" /tmp/qemu_serial_interactive.log; then
    echo "Login prompt reached!"
    # At this point we'd need interactive access
    # The stdio tee approach captures output but we can't send input
fi

# Clean up
kill -9 $QEMU_PID 2>/dev/null || true
echo ""
echo "=== Last 30 lines of serial output ==="
tail -n 30 /tmp/qemu_serial_interactive.log