# Test kernel - exercises 32-bit *W instructions
# Tests: ADDIW, SLLIW, SRLIW, SRAIW, ADDW, SUBW, SLLW, SRLW, SRAW

    .section .text
    .globl _start

_start:
    # Set up UART base
    lui t0, 0x10000      # t0 = 0x10000000 (UART base)

    # Test 1: ADDIW (Add Immediate Word)
    lui t1, 0
    addi t1, t1, -4      # t1 = 0xFFFFFFFFFFFFFFFC (sign-extended)
    addiw t2, t1, 5    # t2 = (0xFFFFFFFC + 5) in 32-bit = 1, then sign-extended to 64-bit
    # Result should be 1 (0x0000000000000001)
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 1)

    # Test 2: ADDIW negative result
    lui t1, 0
    addi t1, t1, 2      # t1 = 2
    addiw t2, t1, -5    # t2 = 2 + (-5) = -3, sign-extended to 0xFFFFFFFFFFFFFFFD
    # But in 32-bit: 0xFFFFFFFD, sign-extended = 0xFFFFFFFFFFFFFFFD
    # We only write the low byte, so we get 0xFD = 253
    sb t2, 0(t0)        # Send to UART (should be 0xFD = 253)

    # Test 3: SLLIW (Shift Left Logical Immediate Word)
    lui t1, 0
    addi t1, t1, 1      # t1 = 1
    slliw t2, t1, 4     # t2 = 1 << 4 = 16, sign-extended = 0x0000000000000010
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 16)

    # Test 4: SRLIW (Shift Right Logical Immediate Word)
    lui t1, 0
    addi t1, t1, 0x80   # t1 = 0x80 (128)
    srliw t2, t1, 4     # t2 = 0x80 >> 4 = 0x08 (8)
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 8)

    # Test 5: SRAIW (Shift Right Arithmetic Immediate Word)
    # Create a negative 32-bit value using ADDIW
    lui t1, 0
    addi t1, t1, 0
    addiw t1, t1, -16   # t1 = -16 in 32-bit = 0xFFFFFFF0, sign-extended to 64-bit
    sraiw t2, t1, 4     # t2 = -16 >> 4 = -1 = 0xFFFFFFFF, low byte = 0xFF = 255
    sb t2, 0(t0)        # Send to UART (should be 255)

    # Test 6: ADDW (Add Word)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 10     # t1 = 10
    addi t2, t2, 3      # t2 = 3
    addw t3, t1, t2     # t3 = 10 + 3 = 13, sign-extended
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 13)

    # Test 7: SUBW (Subtract Word)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 10     # t1 = 10
    addi t2, t2, 3      # t2 = 3
    subw t3, t1, t2     # t3 = 10 - 3 = 7, sign-extended
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 7)

    # Test 8: SLLW (Shift Left Logical Word)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 1      # t1 = 1
    addi t2, t2, 3      # t2 = 3
    sllw t3, t1, t2     # t3 = 1 << 3 = 8
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 8)

    # Test 9: SRLW (Shift Right Logical Word)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 0x80   # t1 = 0x80 (128)
    addi t2, t2, 2      # t2 = 2
    srlw t3, t1, t2     # t3 = 0x80 >> 2 = 0x20 (32)
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 32)

    # Test 10: SRAW (Shift Right Arithmetic Word)
    # Create a negative 32-bit value
    lui t1, 0
    addi t1, t1, 0
    addiw t1, t1, -16   # t1 = -16 in 32-bit, sign-extended to 64-bit
    lui t2, 0
    addi t2, t2, 4      # t2 = 4
    sraw t3, t1, t2     # t3 = -16 >> 4 = -1 = 0xFFFFFFFF, low byte = 0xFF = 255
    sb t3, 0(t0)        # Send to UART (should be 255)

    # Exit
    lui a7, 0
    addi a7, a7, 93      # sys_exit = 93
    ecall

halt:
    j halt