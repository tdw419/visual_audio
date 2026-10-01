.section .text
.global _start

_start:
    li a0, 0xDEAD  # Test value
    li a1, 0xBEEF  # Test value
    add a2, a0, a1  # a2 = 0xDEAD + 0xBEEF = 0x199AC
    slli a3, a2, 4  # a3 = a2 << 4 = 0x199AC0
    srli a4, a2, 8  # a4 = a2 >> 8 = 0x199
    
    # Write to UART (0x10000000)
    li t0, 0x10000000
    sb a0, 0(t0)  # Write 0xAD
    sb a1, 0(t0)  # Write 0xEF
    
hang:
    j hang  # Infinite loop