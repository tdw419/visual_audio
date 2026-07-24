.section .text.init
.global _start
_start:
    la sp, stack_top

    la t0, trap_vector
    csrw mtvec, t0

    j main

.align 4
trap_vector:
    addi sp, sp, -32
    sd ra, 0(sp)
    sd t0, 8(sp)
    sd t1, 16(sp)
    sd t2, 24(sp)

    call c_trap_handler

    ld ra, 0(sp)
    ld t0, 8(sp)
    ld t1, 16(sp)
    ld t2, 24(sp)
    addi sp, sp, 32

    mret
