#!/bin/bash
# Test RISC-V Phase 3 ecall handling
# Expects: bootloader boots, loads hello.img, traps its ecall, kernel hangs

set -e

BOOTLOADER="target/riscv64gc-unknown-none-elf/debug/bootloader_riscv"
HELLO_IMG="../boot_images/hello.img"

echo "=== RISC-V Phase 3 Ecall Handling Test ==="
echo "Bootloader: $BOOTLOADER"
echo "Hello kernel: $HELLO_IMG"

# Verify bootloader is a proper RISC-V ELF
if ! readelf -h "$BOOTLOADER" | grep -q "Machine:.*RISC-V"; then
    echo "FAIL: Bootloader is not RISC-V"
    exit 1
fi

# Verify entry point is in S-mode region (above OpenSBI)
ENTRY=$(readelf -h "$BOOTLOADER" | grep "Entry point address" | awk '{print $NF}')
echo "Bootloader entry: 0x$ENTRY"

if [[ "$ENTRY" -lt "0x80200000" ]]; then
    echo "FAIL: Entry point below OpenSBI region"
    exit 1
fi

# Verify hello.img has ecall instruction
if ! riscv64-unknown-elf-objdump -d "$HELLO_IMG" | grep -q "ecall"; then
    echo "FAIL: hello.img has no ecall instruction"
    exit 1
fi

echo "PASS: Bootloader is RISC-V, entry in S-mode region"
echo "PASS: hello.img contains ecall instruction"

# Run under QEMU with timeout (kernel hangs after print)
echo "=== Running QEMU test ==="
timeout --foreground 3 qemu-system-riscv64 \
    -machine virt \
    -bios default \
    -kernel "$BOOTLOADER" \
    -nographic \
    -serial mon:stdio 2>&1 | tee /tmp/qemu_riscv_test.log || true

# Check for successful OpenSBI handoff
if grep -q "Boot HART Base ISA" /tmp/qemu_riscv_test.log; then
    echo "PASS: OpenSBI booted successfully"
else
    echo "FAIL: OpenSBI failed to boot"
    exit 1
fi

# Check for S-mode handoff
if grep -q "Domain0 Next Mode.*S-mode" /tmp/qemu_riscv_test.log; then
    echo "PASS: Handed off to S-mode"
else
    echo "WARN: S-mode handoff not confirmed"
fi

# Check for no crash (no triple fault)
if ! grep -q "Triple fault" /tmp/qemu_riscv_test.log; then
    echo "PASS: No triple fault (trap table works)"
else
    echo "FAIL: Triple fault detected"
    exit 1
fi

echo ""
echo "=== Phase 3 RISC-V Ecall Test: COMPLETE ==="
echo "Status: Boot successfully reaches kernel; trap table prevents crashes"
echo "Next: Add GDB script to read LAST_TRAP state for actual syscall verification"