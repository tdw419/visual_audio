#!/bin/bash
set -ex

cd /home/jericho/projects/zion/projects/visual_audio/systems/v4_bootloader_x86
cargo build --release --target x86_64-unknown-uefi

# Recreate disk image with fresh bootloader
rm -f /tmp/ubuntu_v4_efi.img
dd if=/usr/share/OVMF/OVMF_VARS_4M.fd of=/tmp/ubuntu_v4_efi.img bs=512 count=9216 conv=notrunc
dd if=target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi of=/tmp/ubuntu_v4_efi.img bs=512 seek=1 conv=notrunc

# Boot QEMU with interactive serial (monitor on stdio, serial on pty)
cd /home/jericho/projects/zion/projects/visual_audio

# Create a named pipe for serial
SERIAL_PIPE=/tmp/qemu_serial_pipe
rm -f $SERIAL_PIPE
mkfifo $SERIAL_PIPE

# Start QEMU with serial to the pipe
qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial pty 2>&1 > /tmp/qemu_monitor.log &

QEMU_PID=$!

# Find the PTY path
sleep 2
PTY_PATH=$(grep "char device redirected to" /tmp/qemu_monitor.log | awk '{print $NF}')
if [ -z "$PTY_PATH" ]; then
    echo "Failed to find PTY path"
    cat /tmp/qemu_monitor.log
    kill -9 $QEMU_PID
    exit 1
fi

echo "Serial PTY: $PTY_PATH"
echo "Waiting 30 seconds for login prompt..."
sleep 30

# Open PTY and send commands
{
    sleep 1
    echo "root"
    sleep 1
    echo "israel"
    sleep 2
    echo "uname -a"
    sleep 1
    echo "cat /etc/os-release | head -3"
    sleep 1
    echo "ls -la /"
    sleep 1
    echo "systemctl is-system-running"
    sleep 1
    echo "exit"
} > "$PTY_PATH"

# Wait a bit more for output
sleep 5

# Kill QEMU
kill -9 $QEMU_PID 2>/dev/null || true

echo ""
echo "=== Monitor log ==="
cat /tmp/qemu_monitor.log | tail -30

echo ""
echo "=== Reading PTY output ==="
cat "$PTY_PATH" 2>/dev/null | tail -50

rm -f $SERIAL_PIPE