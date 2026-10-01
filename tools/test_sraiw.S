# Minimal test for SRAIW - arithmetic right shift of a negative value

    .section .text
    .globl _start

_start:
    # Set up UART base
    lui t0, 0x10000      # t0 = 0x10000000 (UART base)

    # Load a value with bit 7 set (negative in 8-bit signed)
    lui t1, 0
    addi t1, t1, 0xF0   # t1 = 0xF0 (240, which is -16 in signed 8-bit)

    # SRAIW by 4: -16 >> 4 should give -1 (all 1s in 32-bit)
    # -1 in 32-bit is 0xFFFFFFFF
    # Low byte should be 0xFF
    sraiw t2, t1, 4
    sb t2, 0(t0)        # Send low byte (should be 0xFF)

    # Exit
    lui a7, 0
    addi a7, a7, 93      # sys_exit = 93
    ecall

halt:
    j halt