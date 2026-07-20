# Test kernel - writes "Hello" to UART at 0x10000000
# Uses absolute loads for each character

    .section .text
    .globl _start

_start:
    lui t0, 0x10000      # t0 = 0x10000000 (UART base)
    
    # 'H' = 72
    lui a0, 0
    addi a0, a0, 72
    sb a0, 0(t0)
    
    # 'e' = 101
    lui a0, 0
    addi a0, a0, 101
    sb a0, 0(t0)
    
    # 'l' = 108
    lui a0, 0
    addi a0, a0, 108
    sb a0, 0(t0)
    
    # 'l' = 108 (again)
    lui a0, 0
    addi a0, a0, 108
    sb a0, 0(t0)
    
    # 'o' = 111
    lui a0, 0
    addi a0, a0, 111
    sb a0, 0(t0)
    
    # Exit
    lui a7, 0
    addi a7, a7, 93      # sys_exit = 93
    ecall

halt:
    j halt