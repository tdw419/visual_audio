#!/bin/bash
# RISC-V Phase 3 Ecall Test Script
# Verifies trap table intercepts syscalls from loaded kernel

set -e

echo "=== RISC-V Phase 3 Ecall Test ==="
echo ""

# Build the bootloader
echo "Step 1: Building bootloader for riscv64gc-unknown-none-elf..."
cargo build --release --target riscv64gc-unknown-none-elf -p virtio_pixel_rs_v3_riscv
echo "✓ Build complete"
echo ""

# Check embedded payload
echo "Step 2: Verifying embedded hello.img..."
BOOTLOADER="target/riscv64gc-unknown-none-elf/release/bootloader_riscv"
if [ ! -f "$BOOTLOADER" ]; then
    echo "ERROR: Bootloader not found at $BOOTLOADER"
    exit 1
fi

ELF_SIZE=$(stat -c%s "$BOOTLOADER")
echo "✓ Bootloader size: $ELF_SIZE bytes"
echo ""

# Run QEMU test with timeout
echo "Step 3: Running QEMU test (timeout 30s)..."
OUTPUT=$(timeout 30 qemu-system-riscv64 -machine virt -bios default -kernel "$BOOTLOADER" -nographic 2>&1 || true)
echo "$OUTPUT"
echo ""

# Verify critical outputs
echo "Step 4: Verifying test results..."
FAIL=0

if ! echo "$OUTPUT" | grep -q "Trap table initialized"; then
    echo "✗ FAIL: Trap table not initialized"
    FAIL=1
else
    echo "✓ Trap table initialized"
fi

if ! echo "$OUTPUT" | grep -q "Loading embedded ELF (5528 bytes)"; then
    echo "✗ FAIL: Embedded ELF bypass not working"
    FAIL=1
else
    echo "✓ Embedded ELF bypass confirmed (5528 bytes)"
fi

if ! echo "$OUTPUT" | grep -q "Handing off to entry 0x80400000"; then
    echo "✗ FAIL: Kernel handoff failed"
    FAIL=1
else
    echo "✓ Kernel handoff to 0x80400000"
fi

ECALL_COUNT=$(echo "$OUTPUT" | grep -c "TRAP HIT! cause=8" || echo "0")
if [ "$ECALL_COUNT" -eq 0 ]; then
    echo "✗ FAIL: No ecalls intercepted"
    FAIL=1
else
    echo "✓ $ECALL_COUNT ecalls intercepted"
fi

if ! echo "$OUTPUT" | grep -q "Phase 3 complete"; then
    echo "✗ FAIL: Phase 3 did not complete cleanly"
    FAIL=1
else
    echo "✓ Phase 3 completed cleanly"
fi

echo ""

if [ $FAIL -eq 0 ]; then
    echo "=== ALL TESTS PASSED ==="
    exit 0
else
    echo "=== TESTS FAILED ==="
    exit 1
fi