.section .rodata
msg:    .ascii "\n\n*** USERSPACE RUNNING ON THE GPU ***\n\n"
msgend:
.equ msglen, msgend - msg

.section .text
.globl _start
_start:
    li   a7, 64
    li   a0, 1
    la   a1, msg
    li   a2, msglen
    ecall
1:  li   a7, 24
    ecall
    j    1b
