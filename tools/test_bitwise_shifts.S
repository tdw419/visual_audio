# Test kernel - exercises bitwise and shift instructions
# Tests: ANDI, ORI, XORI, SLLI, SRLI, SRAI

    .section .text
    .globl _start

_start:
    # Set up UART base
    lui t0, 0x10000      # t0 = 0x10000000 (UART base)

    # Test 1: ANDI
    lui t1, 0
    addi t1, t1, 0xFF   # t1 = 0xFF (255)
    andi t2, t1, 0x0F   # t2 = 0xFF & 0x0F = 0x0F (15)
    addi a0, t2, 0      # Move t2 to a0
    sb a0, 0(t0)        # Send to UART (should be 15 = 0x0F)

    # Test 2: ORI
    lui t1, 0
    addi t1, t1, 0x30   # t1 = 0x30 (48)
    ori t2, t1, 0x0F    # t2 = 0x30 | 0x0F = 0x3F (63)
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 63 = '?')

    # Test 3: XORI
    lui t1, 0
    addi t1, t1, 0x55   # t1 = 0x55 (85)
    xori t2, t1, 0xFF   # t2 = 0x55 ^ 0xFF = 0xAA (170)
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 170 = 0xAA)

    # Test 4: SLLI (shift left)
    lui t1, 0
    addi t1, t1, 1      # t1 = 1
    slli t2, t1, 4      # t2 = 1 << 4 = 16
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 16 = DLE)

    # Test 5: SRLI (shift right logical)
    lui t1, 0
    addi t1, t1, 0x80   # t1 = 0x80 (128)
    srli t2, t1, 4      # t2 = 0x80 >> 4 = 0x08 (8)
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 8 = backspace)

    # Test 6: SRAI (shift right arithmetic)
    lui t1, 0
    addi t1, t1, 0xF0   # t1 = 0xF0 (240, signed -16)
    srai t2, t1, 4      # t2 = 0xF0 >> 4 (arithmetic) = 0xFF (-1)
    addi a0, t2, 0
    sb a0, 0(t0)        # Send to UART (should be 0xFF = 255)

    # Test 7: AND (register)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 0xFF   # t1 = 0xFF
    addi t2, t2, 0x0F   # t2 = 0x0F
    and t3, t1, t2      # t3 = 0xFF & 0x0F = 0x0F (15)
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 15)

    # Test 8: OR (register)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 0x30   # t1 = 0x30
    addi t2, t2, 0x0F   # t2 = 0x0F
    or t3, t1, t2       # t3 = 0x30 | 0x0F = 0x3F (63)
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 63)

    # Test 9: XOR (register)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 0x55   # t1 = 0x55
    addi t2, t2, 0xFF   # t2 = 0xFF
    xor t3, t1, t2      # t3 = 0x55 ^ 0xFF = 0xAA (170)
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 170)

    # Test 10: SLL (shift left by register)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 1      # t1 = 1
    addi t2, t2, 3      # t2 = 3
    sll t3, t1, t2      # t3 = 1 << 3 = 8
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 8)

    # Test 11: SRL (shift right by register)
    lui t1, 0
    lui t2, 0
    addi t1, t1, 0x80   # t1 = 0x80 (128)
    addi t2, t2, 2      # t2 = 2
    srl t3, t1, t2      # t3 = 0x80 >> 2 = 0x20 (32)
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 32 = space)

    # Test 12: SUB
    lui t1, 0
    lui t2, 0
    addi t1, t1, 10     # t1 = 10
    addi t2, t2, 3      # t2 = 3
    sub t3, t1, t2      # t3 = 10 - 3 = 7
    addi a0, t3, 0
    sb a0, 0(t0)        # Send to UART (should be 7 = bell)

    # Exit
    lui a7, 0
    addi a7, a7, 93      # sys_exit = 93
    ecall

halt:
    j halt