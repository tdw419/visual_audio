
.intel_syntax noprefix
.global _start

.section .text
_start:
    lea rbx, [rip + msg]
.loop:
    movzx rdi, byte ptr [rbx]
    test rdi, rdi
    jz .done
    mov rax, 1
    int 0x80
    inc rbx
    jmp .loop

.done:
    ud2

msg:
    .asciz "\n\n*** HELLO FROM THE SPOKEN KERNEL (x86_64) ***\nBooted via a signed visual-audio boot manifest.\n\n"
