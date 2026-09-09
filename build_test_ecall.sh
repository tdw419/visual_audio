#!/bin/bash
# Simple x86_64 test kernel that makes syscalls via INT 0x80

cat > /tmp/test_ecall.asm << 'EOF'
section .text
global _start

_start:
    # Test sys_write (syscall 4)
    mov rax, 4           # syscall number
    mov rbx, 1           # fd = stdout
    mov rcx, msg_before  # buffer
    mov rdx, msg_len     # length
    int 0x80             # invoke syscall

    # Test sys_exit (syscall 1)
    mov rax, 1           # syscall number
    mov rbx, 0           # exit code 0
    int 0x80             # invoke syscall

section .rodata
msg_before:
    db "BEFORE-ECALL"
msg_len equ $ - msg_before
EOF

nasm -f elf64 /tmp/test_ecall.asm -o /tmp/test_ecall.o
ld /tmp/test_ecall.o -o /tmp/test_ecall --oformat binary -m elf_x86_64 -Ttext 0x200000

echo "Test kernel built: /tmp/test_ecall"
echo "Entry point: 0x200000"
echo "Syscalls: sys_write(4) and sys_exit(1)"