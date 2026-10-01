/* Test ELF binary that makes syscalls via INT 0x80 */

section .text
global _start

_start:
    mov rax, 4           ; syscall number (sys_write)
    mov rbx, 1           ; fd = stdout
    mov rcx, msg         ; buffer
    mov rdx, msg_len     ; length
    int 0x80             ; invoke syscall

    mov rax, 1           ; syscall number (sys_exit)
    mov rbx, 0           ; exit code 0
    int 0x80             ; invoke syscall

section .rodata
msg:
    db "BEFORE-ECALL", 10
msg_len equ $ - msg