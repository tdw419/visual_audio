.section .text.init
.global _start
_start:
    la sp, stack_top
    
    # Set mtvec to our trap vector
    la t0, trap_vector
    csrw mtvec, t0

    j main

.align 4
trap_vector:
    # Save a few registers
    addi sp, sp, -32
    sd ra, 0(sp)
    sd t0, 8(sp)
    sd t1, 16(sp)
    sd t2, 24(sp)

    # Call C trap handler
    call c_trap_handler

    # Restore registers
    ld ra, 0(sp)
    ld t0, 8(sp)
    ld t1, 16(sp)
    ld t2, 24(sp)
    addi sp, sp, 32

    mret
