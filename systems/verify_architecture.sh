#!/bin/bash
# Comprehensive verification script for dual-architecture bootloaders

set -e

echo "=== Dual-Architecture Bootloader Verification ==="
echo ""

# Check shared crate structure
echo "1. Checking shared crate modules..."
SHARED_MODULES="decoder ecall elf64 handoff uart"
for mod in $SHARED_MODULES; do
    if [ -f "virtio_pixel_rs_v3_shared/src/${mod}.rs" ]; then
        echo "  ✓ $mod.rs"
    else
        echo "  ✗ $mod.rs MISSING"
        exit 1
    fi
done
echo ""

# Check RISC-V no longer has shadow modules
echo "2. Checking RISC-V uses shared crate (no shadow modules)..."
RISCV_SHADOW="elf64.rs handoff.rs ecall.rs uart.rs lib.rs"
shadow_found=0
for file in $RISCV_SHADOW; do
    if [ -f "virtio_pixel_rs_v3_riscv/src/$file" ]; then
        echo "  ✗ Shadow module $file still exists"
        shadow_found=1
    fi
done
if [ $shadow_found -eq 0 ]; then
    echo "  ✓ No shadow modules found"
fi
echo ""

# Check x86_64 uses shared crate
echo "3. Checking x86_64 uses shared crate..."
if grep -q "virtio_pixel_rs_v3_shared" virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs; then
    echo "  ✓ x86_64 uses virtio_pixel_rs_v3_shared"
else
    echo "  ✗ x86_64 does NOT use virtio_pixel_rs_v3_shared"
    exit 1
fi
echo ""

# Check trap table timing in x86_64 (setup_trap_table AFTER disk reads)
echo "4. Checking x86_64 trap table timing..."
# Order should be: disk reads → setup_trap_table() → handoff_to_kernel()
setup_line=$(grep -n "setup_trap_table()" virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs | cut -d: -f1)
disk_line=$(grep -n "read_blocks\|Read.*bytes from disk" virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs | tail -1 | cut -d: -f1)
handoff_line=$(grep -n "handoff_to_kernel\|Handing off" virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs | tail -1 | cut -d: -f1)

if [ -n "$setup_line" ] && [ -n "$disk_line" ] && [ -n "$handoff_line" ]; then
    if [ "$setup_line" -gt "$disk_line" ] && [ "$handoff_line" -gt "$setup_line" ]; then
        echo "  ✓ setup_trap_table called AFTER disk reads and BEFORE handoff (CORRECT)"
    else
        echo "  ✗ setup_trap_table timing WRONG (disk=$disk_line, setup=$setup_line, handoff=$handoff_line)"
        exit 1
    fi
else
    echo "  ✗ Could not determine setup_trap_table timing"
    exit 1
fi
echo ""

# Check trap table timing in RISC-V (setup_trap_table AFTER UART init, but it has no disk reads)
echo "5. Checking RISC-V trap table timing (SIE masking in setup_trap_table)..."
if grep -q "csrc sstatus, SSTATUS_SIE" virtio_pixel_rs_v3_shared/src/ecall.rs; then
    echo "  ✓ RISC-V clears SIE in setup_trap_table (CORRECT)"
else
    echo "  ✗ RISC-V does NOT mask supervisor interrupts"
    exit 1
fi
echo ""

# Check interrupt masking in x86_64 IDT setup
echo "6. Checking x86_64 interrupt masking (cli before lidt)..."
if grep -B2 "lidt" virtio_pixel_rs_v3_shared/src/ecall.rs | grep -q "cli"; then
    echo "  ✓ x86_64 masks interrupts before IDT load (CORRECT)"
else
    echo "  ✗ x86_64 does NOT mask interrupts before IDT load"
    exit 1
fi
echo ""

echo "=== All architectural checks PASSED ==="
echo ""
echo "Next: Boot-time verification"
echo "  x86_64: cargo build -p virtio_pixel_rs_v3_x86 --bin bootloader_uefi_x86 --target x86_64-unknown-uefi"
echo "  RISC-V:  cargo build -p virtio_pixel_rs_v3_riscv --release --target riscv64gc-unknown-none-elf"
echo ""
echo "Then run QEMU to verify actual boot behavior."