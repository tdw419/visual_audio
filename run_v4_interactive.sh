#!/bin/bash
set -ex

# Create PTY for bidirectional communication
PTY_IN=$(mktemp -u)
PTY_OUT=$(mktemp -u)
mkfifo $PTY_IN $PTY_OUT

# Start QEMU with serial stdio for interactive login
stty -echo -icanon min 0 time 0

timeout 60s qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial mon:stdio 2>&1 | tee /tmp/qemu_serial_interactive.log &

QEMU_PID=$!

# Wait for login prompt
echo "Waiting for login prompt..."
sleep 20

# Send credentials
echo ""
echo "Attempting login..."
sleep 2
echo "root"
sleep 1
echo "israel"
sleep 3

# Run verification commands
echo ""
echo "Running verification commands..."
sleep 1
echo "uname -a"
sleep 2
echo "cat /etc/os-release"
sleep 2
echo "ls /"
sleep 2
echo "systemctl is-system-running"
sleep 2
echo "exit"
sleep 3

# Cleanup
kill -9 $QEMU_PID || true
rm -f $PTY_IN $PTY_OUT

echo ""
echo "=== Full serial output ==="
tail -n 50 /tmp/qemu_serial_interactive.log