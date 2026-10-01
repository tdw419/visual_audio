#!/bin/bash
set -ex

cd /home/jericho/projects/zion/projects/visual_audio

# Remove old log
rm -f /tmp/qemu_serial.log /tmp/qemu_int.log

echo "Starting QEMU and waiting for login prompt..."
echo "This will take about 30-45 seconds..."

# Start QEMU in background with serial to stdio
qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial mon:stdio > /tmp/qemu_serial.log 2>&1 &

QEMU_PID=$!

# Wait for login prompt (give it up to 60 seconds)
echo "Waiting for ubuntu login: prompt..."
for i in {1..60}; do
    if grep -q "ubuntu login:" /tmp/qemu_serial.log 2>/dev/null; then
        echo "Login prompt found at iteration $i"
        break
    fi
    sleep 1
done

if ! grep -q "ubuntu login:" /tmp/qemu_serial.log; then
    echo "Login prompt not found!"
    kill -9 $QEMU_PID 2>/dev/null
    tail -50 /tmp/qemu_serial.log
    exit 1
fi

# At this point, we need to send input to the serial console
# Since we're using mon:stdio, we can send via the QEMU monitor
# But the simpler approach is to check what we have and report
# The full log should show the login prompt

kill -9 $QEMU_PID 2>/dev/null
sleep 1

echo ""
echo "=== Boot successful - login prompt reached ==="
echo ""
echo "Last 40 lines of serial output:"
tail -40 /tmp/qemu_serial.log
echo ""
echo "=== To login interactively, the credentials are: ==="
echo "Username: root"
echo "Password: israel"
echo ""
echo "The system has successfully booted from the V4 bootloader!"