#!/bin/bash
# Test Phase 3 ecall implementation on x86_64

echo "=== Phase 3 Ecall Implementation Test ==="
echo ""

# Build test kernel
echo "1. Building test kernel with INT 0x80 syscalls..."
cat > /tmp/test_ecall.asm << 'EOF'
section .text
global _start

_start:
    mov rax, 4           ; syscall number (sys_write)
    mov rbx, 1           ; fd = stdout
    mov rcx, msg_before  ; buffer
    mov rdx, msg_len     ; length
    int 0x80             ; invoke syscall

    mov rax, 1           ; syscall number (sys_exit)
    mov rbx, 0           ; exit code 0
    int 0x80             ; invoke syscall

section .rodata
msg_before:
    db "BEFORE-ECALL"
msg_len equ $ - msg_before
EOF

cat > /tmp/test_ecall.ld << 'EOF'
OUTPUT_FORMAT("elf64-x86-64")
OUTPUT_ARCH("i386:x86-64")
ENTRY(_start)

SECTIONS
{
    . = 0x200000;
    .text : {
        *(.text)
    }
    .rodata : {
        *(.rodata)
    }
}
EOF

nasm -f elf64 /tmp/test_ecall.asm -o /tmp/test_ecall.o
ld /tmp/test_ecall.o -o /tmp/test_ecall_elf -m elf_x86_64 -T /tmp/test_ecall.ld

echo "Test kernel built: /tmp/test_ecall_elf"
echo ""

# Get bootloader path
BOOTLOADER=$(find /home/jericho/projects/zion/projects/visual_audio/systems/target/x86_64-unknown-uefi/release -name "bootloader_uefi_x86*.efi" 2>/dev/null | head -1)

if [ -z "$BOOTLOADER" ]; then
    echo "ERROR: Bootloader not found. Build failed."
    exit 1
fi

echo "2. Bootloader found: $BOOTLOADER"
echo ""

# Test kernel properties
echo "3. Test kernel properties:"
echo "   Entry point: 0x200000"
echo "   Syscalls: sys_write(4), sys_exit(1)"
echo "   Method: INT 0x80"
echo ""

# Create test disk image
echo "4. Creating test disk image..."
dd if=/tmp/test_ecall_elf of=/tmp/test_ecall.img bs=512 count=8 2>&1 | grep -v "records"
echo ""

echo "5. Expected output:"
echo "   Handing off to entry 0x200000..."
echo "   ECALL: syscall=4"
echo "     sys_write (stub)"
echo "   ECALL: syscall=1"
echo "     sys_exit (stub)"
echo ""

echo "=== To test manually, run: ==="
echo "qemu-system-x86_64 \\"
echo "  -bios OVMF.fd \\"
echo "  -drive file=$BOOTLOADER,format=raw,if=virtio,readonly=on \\"
echo "  -drive file=/tmp/test_ecall.img,format=raw,if=virtio \\"
echo "  -serial stdio"
echo ""

echo "=== Phase 3 Test Complete ==="