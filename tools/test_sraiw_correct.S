# Corrected test for SRAIW - arithmetic right shift of a negative value

    .section .text
    .globl _start

_start:
    # Set up UART base
    lui t0, 0x10000      # t0 = 0x10000000 (UART base)

    # Load a signed negative value using 32-bit load
    # We'll use ADDIW with a negative immediate to create a sign-extended 64-bit value
    lui t1, 0
    addi t1, t1, 0
    addiw t1, t1, -16    # t1 = -16 in 32-bit = 0xFFFFFFF0, sign-extended to 64-bit

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