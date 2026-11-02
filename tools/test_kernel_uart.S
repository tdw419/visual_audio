# Test kernel that outputs to UART at 0x10000000
# Writes "Hello" to UART character by character

    .section .text
    .globl _start

_start:
    lui t0, 0x10000      # t0 = 0x10000000 (UART base)
    
    lui a0, 0
    addi a0, a0, 72      # 'H' = 72
    sb a0, 0(t0)
    
    addi a0, a0, 29      # 'e' = 101
    sb a0, 0(t0)
    
    addi a0, a0, 11      # 'l' = 108
    sb a0, 0(t0)
    
    sb a0, 0(t0)         # 'l' again
    
    addi a0, a0, 11      # 'o' = 111
    sb a0, 0(t0)
    
    # Exit
    lui a7, 0
    addi a7, a7, 93      # sys_exit = 93
    ecall

halt:
    j halt