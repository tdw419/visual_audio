.section .text.init
.global _start
_start:
    # Set up stack pointer
    la sp, stack_top
    
    # Set up trap handler
    la t0, trap_handler
    csrw mtvec, t0
    
    # Jump to main
    j main

.global trap_handler
.align 4
trap_handler:
    # Save a0 on stack
    addi sp, sp, -16
    sd a0, 0(sp)
    
    # Call C trap handler
    call handle_trap
    
    # Restore a0
    ld a0, 0(sp)
    addi sp, sp, 16
    
    # Return from machine trap
    mret
