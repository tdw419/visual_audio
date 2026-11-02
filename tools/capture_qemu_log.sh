#!/bin/bash
# Simple QEMU state capture using monitor interface and QEMU log

# Kill any existing QEMU on port 1234
pkill -9 qemu-system-riscv64 2>/dev/null
sleep 1

# Start QEMU with logging
echo "Starting QEMU with logging..."
qemu-system-riscv64 \
    -nographic \
    -machine virt \
    -kernel boot_images/alpine_Image \
    -initrd boot_images/alpine_initrd \
    -m 512M \
    -d in_asm,exec,cpu_reset \
    -D /tmp/qemu_boot.log \
    -serial mon:stdio &
QEMU_PID=$!

echo "QEMU PID: $QEMU_PID"
echo "Logging to /tmp/qemu_boot.log"

# Wait for QEMU to reach the instruction
echo "Waiting 30 seconds for boot..."
sleep 30

# Kill QEMU
echo "Stopping QEMU..."
kill $QEMU_PID 2>/dev/null
sleep 2
kill -9 $QEMU_PID 2>/dev/null

# Extract the instruction sequence around 0x80201048
echo "Extracting instruction sequence..."
grep -A 5 -B 5 "80201048" /tmp/qemu_boot.log > qemu_seq_at_0x80201048.txt 2>/dev/null

# Also capture full log for reference
cp /tmp/qemu_boot.log qemu_full_boot.log

if [ -f qemu_seq_at_0x80201048.txt ] && [ -s qemu_seq_at_0x80201048.txt ]; then
    echo "✓ Instruction sequence captured to qemu_seq_at_0x80201048.txt"
    head -50 qemu_seq_at_0x80201048.txt
else
    echo "✗ Instruction sequence not found in log"
    echo "Checking if 0x80201048 was reached..."
    grep -c "80201048" /tmp/qemu_boot.log || echo "0 hits"
fi

echo "Full log saved to qemu_full_boot.log"
echo "✓ QEMU capture complete!"